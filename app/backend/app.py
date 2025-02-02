import dataclasses
import datetime
import io
import json
import mimetypes
import os
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Union, cast, List
import logging
from azure.core.credentials import AzureKeyCredential
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from azure.keyvault.secrets.aio import SecretClient
from azure.monitor.opentelemetry import configure_azure_monitor
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.storage.blob.aio import ContainerClient
from azure.storage.blob.aio import StorageStreamDownloader as BlobDownloader
from azure.storage.filedatalake.aio import FileSystemClient
from azure.storage.filedatalake.aio import StorageStreamDownloader as DatalakeDownloader
from openai import AsyncAzureOpenAI, AsyncOpenAI
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.instrumentation.httpx import (
    HTTPXClientInstrumentor,
)
from opentelemetry.instrumentation.openai import OpenAIInstrumentor
from quart import (
    Blueprint,
    Quart,
    abort,
    current_app,
    jsonify,
    make_response,
    request,
    send_file,
    send_from_directory,
)
from quart_cors import cors

from approaches.approach import Approach
from approaches.chatreadretrieveread import ChatReadRetrieveReadApproach
from approaches.chatreadretrievereadvision import ChatReadRetrieveReadVisionApproach
from approaches.retrievethenread import RetrieveThenReadApproach
from approaches.retrievethenreadvision import RetrieveThenReadVisionApproach
from config import (
    CONFIG_ASK_APPROACH,
    CONFIG_ASK_VISION_APPROACH,
    CONFIG_AUTH_CLIENT,
    CONFIG_BLOB_CONTAINER_CLIENT,
    CONFIG_CHAT_APPROACH,
    CONFIG_CHAT_VISION_APPROACH,
    CONFIG_GPT4V_DEPLOYED,
    CONFIG_INGESTER,
    CONFIG_OPENAI_CLIENT,
    CONFIG_SEARCH_CLIENT,
    CONFIG_SEMANTIC_RANKER_DEPLOYED,
    CONFIG_USER_BLOB_CONTAINER_CLIENT,
    CONFIG_USER_UPLOAD_ENABLED,
    CONFIG_VECTOR_SEARCH_ENABLED,
    CONFIG_SHOW_SUPPORTING_CONTENT,
    CONFIG_SHOW_THOUGHT_PROCESS
)
from cachetools import TTLCache
from core.theme.application.use_cases.list_themes import ListTheme
from core.authentication import AuthenticationHelper
from decorators import authenticated, authenticated_path
from error import error_dict, error_response
from services.cosmosDB.cosmosRepository import CosmosRepository
from services.cosmosDB.repositories.cosmosDB_theme_repository import ThemeRepository
from prepdocs import (
    clean_key_if_exists,
    setup_embeddings_service,
    setup_file_processors,
    setup_search_info,
)
from prepdocslib.filestrategy import UploadUserFileStrategy
from prepdocslib.listfilestrategy import File
from azure.storage.blob import generate_blob_sas, BlobSasPermissions, BlobClient, BlobServiceClient, generate_blob_sas

bp = Blueprint("routes", __name__, static_folder="static")
# Fix Windows registry issue with mimetypes
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
logging.basicConfig(level=logging.INFO)
# Define a cache with a maximum size and TTL of 24 hours (86400 seconds)
cache = TTLCache(maxsize=100, ttl=24 * 3600)


def add_to_cache(key, value):
    cache[key] = value


def get_from_cache(key):
    return cache.get(key, None)

@bp.route("/")
async def index():
    return await bp.send_static_file("index.html")


# Empty page is recommended for login redirect to work.
# See https://github.com/AzureAD/microsoft-authentication-library-for-js/blob/dev/lib/msal-browser/docs/initialization.md#redirecturi-considerations for more information
@bp.route("/redirect")
async def redirect():
    return ""


@bp.route("/favicon.ico")
async def favicon():
    return await bp.send_static_file("favicon.ico")


@bp.route("/assets/<path:path>")
async def assets(path):
    return await send_from_directory(Path(__file__).resolve().parent / "static" / "assets", path)


@bp.route("/content")
@authenticated_path
async def content_file(file: str, auth_claims: Dict[str, Any]):
    """
    Serve content files from blob storage from within the app to keep the example self-contained.
    *** NOTE *** if you are using app services authentication, this route will return unauthorized to all users that are not logged in
    if AZURE_ENFORCE_ACCESS_CONTROL is not set or false, logged in users can access all files regardless of access control
    if AZURE_ENFORCE_ACCESS_CONTROL is set to true, logged in users can only access files they have access to
    This is also slow and memory hungry.
    """
    # Remove page number from path, filename-1.txt -> filename.txt
    # This shouldn't typically be necessary as browsers don't send hash fragments to servers
    path = request.args.get('file', default='', type=str)
    
    if path.find("#page=") > 0:
        path_parts = path.rsplit("#page=", 1)
        path = path_parts[0]
    logging.info(f"Opening file {path}")
    blob_container_client: ContainerClient = current_app.config[CONFIG_BLOB_CONTAINER_CLIENT]
    blob: Union[BlobDownloader, DatalakeDownloader]
    try:
        blob = await blob_container_client.get_blob_client(path).download_blob()
    except ResourceNotFoundError:
        logging.info(f"Path not found in general Blob container: {path}", )
        if current_app.config[CONFIG_USER_UPLOAD_ENABLED]:  
            try:
                user_oid = auth_claims["oid"]
                user_blob_container_client = current_app.config[CONFIG_USER_BLOB_CONTAINER_CLIENT]
                user_directory_client: FileSystemClient = user_blob_container_client.get_directory_client(user_oid)
                file_client = user_directory_client.get_file_client(path)
                blob = await file_client.download_file()
            except ResourceNotFoundError:
                logging.error(f"Path not found in DataLake: {str(path)}")
                abort(404)
        else:
            abort(404)
    if not blob.properties or not blob.properties.has_key("content_settings"):
        abort(404)
    mime_type = blob.properties["content_settings"]["content_type"]
    if mime_type == "application/octet-stream":
        mime_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    blob_file = io.BytesIO()
    await blob.readinto(blob_file)
    blob_file.seek(0)
    return await send_file(blob_file, mimetype=mime_type, as_attachment=False, attachment_filename=path)

@bp.route("/clearcache", methods=["POST"])
async def clear_cache():
    cache.clear()
    return jsonify({"message": "Cache cleared"}), 200


@bp.route("/ask", methods=["POST"])
@authenticated
async def ask(auth_claims: Dict[str, Any]):
    if not request.is_json:
        return jsonify({"error": "request must be json"}), 415
    request_json = await request.get_json()
    context = request_json.get("context", {})
    context["auth_claims"] = auth_claims
    try:
        use_gpt4v = context.get("overrides", {}).get("use_gpt4v", False)
        approach: Approach
        if use_gpt4v and CONFIG_ASK_VISION_APPROACH in current_app.config:
            approach = cast(Approach, current_app.config[CONFIG_ASK_VISION_APPROACH])
        else:
            approach = cast(Approach, current_app.config[CONFIG_ASK_APPROACH])
        r = await approach.run(
            request_json["messages"], context=context, session_state=request_json.get("session_state")
        )
        return jsonify(r)
    except Exception as error:
        return error_response(error, "/ask")


class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)

cosmos_repository = None

if os.getenv("MONGODB_CONN_STRING"):
        DATABASE_NAME = os.getenv('DATABASE_NAME')
        CONN_STRING = os.getenv('MONGODB_CONN_STRING')
        cosmos_repository = CosmosRepository(connection_string=CONN_STRING, database_name=DATABASE_NAME)

async def format_as_ndjson(r: AsyncGenerator[dict, None]) -> AsyncGenerator[str, None]:
    try:
        async for event in r:
            yield json.dumps(event, ensure_ascii=False, cls=JSONEncoder) + "\n"
    except Exception as error:
        logging.error(f"Exception while generating response stream: {str(error)}")

        yield json.dumps(error_dict(error))

async def fetch_themes() -> List[Dict[str, Any]]:
    themes = get_from_cache("themes")

    if not themes:
        if not cosmos_repository:
            return jsonify({'error': 'Cosmos DB not configured'}), 400

        else:
            use_case = ListTheme(ThemeRepository(cosmos_repository))
            try:
                response = use_case.execute()
                themes_json = [theme.to_dict() for theme in response.data]
                logging.info("Themes retrieved successfully")
                add_to_cache("themes", themes_json)
                logging.info("Themes cached successfully")
                themes = themes_json
            except Exception as e:
                logging.error(f"Error getting themes: {str(e)}")
                return jsonify({'error': str(e)}), 400

    return themes



@bp.route("/themes", methods=["GET"])
async def themes():
    if get_from_cache("themes"):
        return get_from_cache("themes"), 200

    return await fetch_themes()


@bp.route("/chat", methods=["POST"])
@authenticated
async def chat(auth_claims: Dict[str, Any]):
    
    if not request.is_json:
        return jsonify({"error": "request must be json"}), 415
    request_json = await request.get_json()
    context = request_json.get("context", {})
    context["auth_claims"] = auth_claims

    theme_id = context["overrides"]["theme_id"]
    
    if not theme_id:
        return jsonify({'error': 'theme_id not found'}), 400
    
    themes = await fetch_themes()

    selected_theme = next(
        (theme for theme in themes if theme["themeId"] == theme_id), None)

    if not selected_theme:
        return jsonify({'error': 'Theme not found'}), 400

    AZURE_SEARCH_SERVICE = os.environ["AZURE_SEARCH_SERVICE"]
    AZURE_KEY_VAULT_NAME = os.getenv("AZURE_KEY_VAULT_NAME")
    AZURE_SEARCH_SECRET_NAME = os.getenv("AZURE_SEARCH_SECRET_NAME")

    # azure_credential = DefaultAzureCredential(
    #     exclude_shared_token_cache_credential=True)

    # # Fetch any necessary secrets from Key Vault
    # search_key = None
    # if AZURE_KEY_VAULT_NAME:
    #     async with SecretClient(
    #         vault_url=f"https://{AZURE_KEY_VAULT_NAME}.vault.azure.net", credential=azure_credential
    #     ) as key_vault_client:
    #         search_key = (
    #             # type: ignore[attr-defined]
    #             AZURE_SEARCH_SECRET_NAME and (await key_vault_client.get_secret(AZURE_SEARCH_SECRET_NAME)).value
    #         )

    # # Set up clients for AI Search and Storage
    # search_credential: Union[AsyncTokenCredential, AzureKeyCredential] = (
    #     AzureKeyCredential(search_key) if search_key else azure_credential
    # )

    AZURE_SEARCH_SERVICE_QUERY_KEY = os.environ["AZURE_SEARCH_SERVICE_QUERY_KEY"]

    if not AZURE_SEARCH_SERVICE_QUERY_KEY:
        return jsonify({'error': 'Azure Search Service Query Key not found'}), 400
    
    if not AZURE_SEARCH_SERVICE:
        return jsonify({'error': 'Azure Search Service not found'}), 400
    
    index_name = selected_theme["assistantConfig"]["searchIndexName"]

    if not index_name:
        return jsonify({'error': 'Index name not found'}), 400

    search_client = SearchClient(
        endpoint=f"https://{AZURE_SEARCH_SERVICE}.search.windows.net",
        index_name=index_name,
        credential=AzureKeyCredential(AZURE_SEARCH_SERVICE_QUERY_KEY),
    )

    current_app.config[CONFIG_CHAT_APPROACH].set_search_client(search_client)
    current_app.config[CONFIG_SEARCH_CLIENT] = search_client

    try:
        use_gpt4v = context.get("overrides", {}).get("use_gpt4v", False)
        approach: Approach
        if use_gpt4v and CONFIG_CHAT_VISION_APPROACH in current_app.config:
            approach = cast(
                Approach, current_app.config[CONFIG_CHAT_VISION_APPROACH])
        else:
            approach = cast(Approach, current_app.config[CONFIG_CHAT_APPROACH])

        result = await approach.run(
            request_json["messages"],
            theme=selected_theme,
            stream=request_json.get("stream", False),
            context=context,
            session_state=request_json.get("session_state"),
        )
        if isinstance(result, dict):
            return jsonify(result)
        else:
            response = await make_response(format_as_ndjson(result))
            response.timeout = None  # type: ignore
            response.mimetype = "application/json-lines"
            return response
    except Exception as error:
        return error_response(error, "/chat")

# Send MSAL.js settings to the client UI
@bp.route("/auth_setup", methods=["GET"])
def auth_setup():
    auth_helper = current_app.config[CONFIG_AUTH_CLIENT]
    return jsonify(auth_helper.get_auth_setup_for_client())


@bp.route("/config", methods=["GET"])
def config():
    return jsonify(
        {
            "showGPT4VOptions": current_app.config[CONFIG_GPT4V_DEPLOYED],
            "showSemanticRankerOption": current_app.config[CONFIG_SEMANTIC_RANKER_DEPLOYED],
            "showVectorOption": current_app.config[CONFIG_VECTOR_SEARCH_ENABLED],
            "showUserUpload": current_app.config[CONFIG_USER_UPLOAD_ENABLED],
            "showThoughtProcess": current_app.config[CONFIG_SHOW_THOUGHT_PROCESS],
            "showSupportingContent": current_app.config[CONFIG_SHOW_SUPPORTING_CONTENT],
        }
    )


@bp.post("/upload")
@authenticated
async def upload(auth_claims: dict[str, Any]):
    request_files = await request.files
    if "file" not in request_files:
        # If no files were included in the request, return an error response
        return jsonify({"message": "No file part in the request", "status": "failed"}), 400

    user_oid = auth_claims["oid"]
    file = request_files.getlist("file")[0]
    user_blob_container_client: FileSystemClient = current_app.config[CONFIG_USER_BLOB_CONTAINER_CLIENT]
    user_directory_client = user_blob_container_client.get_directory_client(user_oid)
    try:
        await user_directory_client.get_directory_properties()
    except ResourceNotFoundError:
        current_app.logger.info("Creating directory for user %s", user_oid)
        await user_directory_client.create_directory()
    await user_directory_client.set_access_control(owner=user_oid)
    file_client = user_directory_client.get_file_client(file.filename)
    file_io = file
    file_io.name = file.filename
    file_io = io.BufferedReader(file_io)
    await file_client.upload_data(file_io, overwrite=True, metadata={"UploadedBy": user_oid})
    file_io.seek(0)
    ingester: UploadUserFileStrategy = current_app.config[CONFIG_INGESTER]
    await ingester.add_file(File(content=file_io, acls={"oids": [user_oid]}, url=file_client.url))
    return jsonify({"message": "File uploaded successfully"}), 200


@bp.post("/delete_uploaded")
@authenticated
async def delete_uploaded(auth_claims: dict[str, Any]):
    request_json = await request.get_json()
    filename = request_json.get("filename")
    user_oid = auth_claims["oid"]
    user_blob_container_client: FileSystemClient = current_app.config[CONFIG_USER_BLOB_CONTAINER_CLIENT]
    user_directory_client = user_blob_container_client.get_directory_client(user_oid)
    file_client = user_directory_client.get_file_client(filename)
    await file_client.delete_file()
    ingester = current_app.config[CONFIG_INGESTER]
    await ingester.remove_file(filename, user_oid)
    return jsonify({"message": f"File {filename} deleted successfully"}), 200


@bp.get("/list_uploaded")
@authenticated
async def list_uploaded(auth_claims: dict[str, Any]):
    user_oid = auth_claims["oid"]
    user_blob_container_client: FileSystemClient = current_app.config[CONFIG_USER_BLOB_CONTAINER_CLIENT]
    files = []
    try:
        all_paths = user_blob_container_client.get_paths(path=user_oid)
        async for path in all_paths:
            files.append(path.name.split("/", 1)[1])
    except ResourceNotFoundError as error:
        if error.status_code != 404:
            current_app.logger.exception("Error listing uploaded files", error)
    return jsonify(files), 200

@bp.route("/content-original")
async def content_file_original():
    path = request.args.get('file', default='', type=str)
    fragment = request.args.get('fragment', default='', type=str)

    AZURE_STORAGE_CONTAINER_ORIGINAL_DOCUMENTS = os.environ.get("AZURE_STORAGE_CONTAINER_ORIGINAL_DOCUMENTS", "originaldocuments")
    blob_container_client: ContainerClient = current_app.config[AZURE_STORAGE_CONTAINER_ORIGINAL_DOCUMENTS]
    try:
        logging.info(f"Opening {path}")
        blob_client = blob_container_client.get_blob_client(path)
        # Generate SAS token
        sas_token = generate_blob_sas(
            account_name=blob_client.account_name,
            container_name=blob_client.container_name,
            blob_name=blob_client.blob_name,
            account_key=blob_container_client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)  # Token valid for 10 mins
        )  
            
        blob_url = blob_client.url + "?" + sas_token + "#" + fragment
        return jsonify({"url": blob_url}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    

@bp.before_app_serving
async def setup_clients():
    # Replace these with your own values, either in environment variables or directly here
    AZURE_STORAGE_ACCOUNT = os.environ["AZURE_STORAGE_ACCOUNT"]
    AZURE_STORAGE_CONTAINER_ORIGINAL_DOCUMENTS = os.environ.get("AZURE_STORAGE_CONTAINER_ORIGINAL_DOCUMENTS", "originaldocuments")
    AZURE_STORAGE_CONTAINER = os.environ["AZURE_STORAGE_CONTAINER"]
    AZURE_USERSTORAGE_ACCOUNT = os.environ.get("AZURE_USERSTORAGE_ACCOUNT")
    AZURE_USERSTORAGE_CONTAINER = os.environ.get("AZURE_USERSTORAGE_CONTAINER")
    AZURE_SEARCH_SERVICE = os.environ["AZURE_SEARCH_SERVICE"]
    AZURE_SEARCH_INDEX = os.environ["AZURE_SEARCH_INDEX"]
    AZURE_SEARCH_SECRET_NAME = os.getenv("AZURE_SEARCH_SECRET_NAME")
    AZURE_KEY_VAULT_NAME = os.getenv("AZURE_KEY_VAULT_NAME")
    # Shared by all OpenAI deployments
    OPENAI_HOST = os.getenv("OPENAI_HOST", "azure")
    OPENAI_CHATGPT_MODEL = os.environ["AZURE_OPENAI_CHATGPT_MODEL"]
    OPENAI_EMB_MODEL = os.getenv("AZURE_OPENAI_EMB_MODEL_NAME", "text-embedding-ada-002")
    OPENAI_EMB_DIMENSIONS = int(os.getenv("AZURE_OPENAI_EMB_DIMENSIONS", 1536))
    # Used with Azure OpenAI deployments
    AZURE_OPENAI_SERVICE = os.getenv("AZURE_OPENAI_SERVICE")
    AZURE_OPENAI_GPT4V_DEPLOYMENT = os.environ.get("AZURE_OPENAI_GPT4V_DEPLOYMENT")
    AZURE_OPENAI_GPT4V_MODEL = os.environ.get("AZURE_OPENAI_GPT4V_MODEL")
    AZURE_OPENAI_CHATGPT_DEPLOYMENT = (
        os.getenv("AZURE_OPENAI_CHATGPT_DEPLOYMENT") if OPENAI_HOST.startswith("azure") else None
    )
    AZURE_OPENAI_EMB_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMB_DEPLOYMENT") if OPENAI_HOST.startswith("azure") else None
    AZURE_VISION_ENDPOINT = os.getenv("AZURE_VISION_ENDPOINT", "")
    # Used only with non-Azure OpenAI deployments
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_ORGANIZATION = os.getenv("OPENAI_ORGANIZATION")

    AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID")
    AZURE_USE_AUTHENTICATION = os.getenv("AZURE_USE_AUTHENTICATION", "").lower() == "true"
    AZURE_ENFORCE_ACCESS_CONTROL = os.getenv("AZURE_ENFORCE_ACCESS_CONTROL", "false").lower() == "true"
    AZURE_ENABLE_GLOBAL_DOCUMENT_ACCESS = os.getenv("AZURE_ENABLE_GLOBAL_DOCUMENT_ACCESS", "true").lower() == "true"
    AZURE_ENABLE_UNAUTHENTICATED_ACCESS = os.getenv("AZURE_ENABLE_UNAUTHENTICATED_ACCESS", "false").lower() == "true"
    AZURE_SERVER_APP_ID = os.getenv("AZURE_SERVER_APP_ID")
    CHATAPP_API_AZURE_CLIENT_SECRET = os.getenv("CHATAPP_API_AZURE_CLIENT_SECRET")
    AZURE_CLIENT_APP_ID = os.getenv("AZURE_CLIENT_APP_ID")
    AZURE_AUTH_TENANT_ID = os.getenv("AZURE_AUTH_TENANT_ID", AZURE_TENANT_ID)

    KB_FIELDS_CONTENT = os.getenv("KB_FIELDS_CONTENT", "content")
    KB_FIELDS_SOURCEPAGE = os.getenv("KB_FIELDS_SOURCEPAGE", "sourcepage")

    AZURE_SEARCH_QUERY_LANGUAGE = os.getenv("AZURE_SEARCH_QUERY_LANGUAGE", "en-us")
    AZURE_SEARCH_QUERY_SPELLER = os.getenv("AZURE_SEARCH_QUERY_SPELLER", "lexicon")
    AZURE_SEARCH_SEMANTIC_RANKER = os.getenv("AZURE_SEARCH_SEMANTIC_RANKER", "free").lower()

    USE_GPT4V = os.getenv("USE_GPT4V", "").lower() == "true"
    USE_USER_UPLOAD = os.getenv("USE_USER_UPLOAD", "").lower() == "true"

    # Use the current user identity to authenticate with Azure OpenAI, AI Search and Blob Storage (no secrets needed,
    # just use 'az login' locally, and managed identity when deployed on Azure). If you need to use keys, use separate AzureKeyCredential instances with the
    # keys for each service
    # If you encounter a blocking error during a DefaultAzureCredential resolution, you can exclude the problematic credential by using a parameter (ex. exclude_shared_token_cache_credential=True)
    azure_credential = DefaultAzureCredential(exclude_shared_token_cache_credential=True)

    # Fetch any necessary secrets from Key Vault
    search_key = None
    if AZURE_KEY_VAULT_NAME:
        async with SecretClient(
            vault_url=f"https://{AZURE_KEY_VAULT_NAME}.vault.azure.net", credential=azure_credential
        ) as key_vault_client:
            search_key = (
                AZURE_SEARCH_SECRET_NAME and (await key_vault_client.get_secret(AZURE_SEARCH_SECRET_NAME)).value  # type: ignore[attr-defined]
            )
    
    AZURE_OPENAISERVICE_KEY = os.getenv("AZURE_OPENAISERVICE_KEY")
    # Set up clients for AI Search and Storage
    search_credential: Union[AsyncTokenCredential, AzureKeyCredential] = (
        AzureKeyCredential(search_key) if search_key else azure_credential
    )
    search_client = SearchClient(
        endpoint=f"https://{AZURE_SEARCH_SERVICE}.search.windows.net",
        index_name=AZURE_SEARCH_INDEX,
        credential=search_credential,
    )

    BLOB_CONTAINER_CLIENT_CONNECTION_STRING = os.getenv("AZURE_STORAGE_ACCOUNT_CONN_STRING")
    blob_container_client = ContainerClient.from_connection_string(
        conn_str=BLOB_CONTAINER_CLIENT_CONNECTION_STRING, container_name=AZURE_STORAGE_CONTAINER
    )

    blob_container_original_documents_client = ContainerClient.from_connection_string(
        conn_str=BLOB_CONTAINER_CLIENT_CONNECTION_STRING, container_name=AZURE_STORAGE_CONTAINER_ORIGINAL_DOCUMENTS
    )

    # Set up authentication helper
    search_index = None
    if AZURE_USE_AUTHENTICATION and AZURE_ENFORCE_ACCESS_CONTROL:
        search_index_client = SearchIndexClient(
            endpoint=f"https://{AZURE_SEARCH_SERVICE}.search.windows.net",
            credential=search_credential,
        )
        search_index = await search_index_client.get_index(AZURE_SEARCH_INDEX)
        await search_index_client.close()
    auth_helper = AuthenticationHelper(
        search_index=search_index,
        use_authentication=AZURE_USE_AUTHENTICATION,
        server_app_id=AZURE_SERVER_APP_ID,
        server_app_secret=CHATAPP_API_AZURE_CLIENT_SECRET,
        client_app_id=AZURE_CLIENT_APP_ID,
        tenant_id=AZURE_AUTH_TENANT_ID,
        require_access_control=AZURE_ENFORCE_ACCESS_CONTROL,
        enable_global_documents=AZURE_ENABLE_GLOBAL_DOCUMENT_ACCESS,
        enable_unauthenticated_access=AZURE_ENABLE_UNAUTHENTICATED_ACCESS,
    )

    if USE_USER_UPLOAD:
        current_app.logger.info("USE_USER_UPLOAD is true, setting up user upload feature")
        if not AZURE_USERSTORAGE_ACCOUNT or not AZURE_USERSTORAGE_CONTAINER:
            raise ValueError(
                "AZURE_USERSTORAGE_ACCOUNT and AZURE_USERSTORAGE_CONTAINER must be set when USE_USER_UPLOAD is true"
            )
        user_blob_container_client = FileSystemClient(
            f"https://{AZURE_USERSTORAGE_ACCOUNT}.dfs.core.windows.net",
            AZURE_USERSTORAGE_CONTAINER,
            credential=azure_credential,
        )
        current_app.config[CONFIG_USER_BLOB_CONTAINER_CLIENT] = user_blob_container_client

        # Set up ingester
        file_processors = setup_file_processors(
            azure_credential=azure_credential,
            document_intelligence_service=os.getenv("AZURE_DOCUMENTINTELLIGENCE_SERVICE"),
            local_pdf_parser=os.getenv("USE_LOCAL_PDF_PARSER", "").lower() == "true",
            local_html_parser=os.getenv("USE_LOCAL_HTML_PARSER", "").lower() == "true",
            search_images=USE_GPT4V,
        )
        search_info = await setup_search_info(
            search_service=AZURE_SEARCH_SERVICE,
            index_name=AZURE_SEARCH_INDEX,
            azure_credential=azure_credential,
            search_key=clean_key_if_exists(search_key),
        )
        text_embeddings_service = setup_embeddings_service(
            azure_credential=azure_credential,
            openai_host=OPENAI_HOST,
            openai_model_name=OPENAI_EMB_MODEL,
            openai_service=AZURE_OPENAI_SERVICE,
            openai_deployment=AZURE_OPENAI_EMB_DEPLOYMENT,
            openai_dimensions=OPENAI_EMB_DIMENSIONS,
            openai_key=clean_key_if_exists(OPENAI_API_KEY),
            openai_org=OPENAI_ORGANIZATION,
            disable_vectors=os.getenv("USE_VECTORS", "").lower() == "false",
        )
        ingester = UploadUserFileStrategy(
            search_info=search_info, embeddings=text_embeddings_service, file_processors=file_processors
        )
        current_app.config[CONFIG_INGESTER] = ingester

    # Used by the OpenAI SDK
    openai_client: AsyncOpenAI

    if OPENAI_HOST.startswith("azure"):
        # token_provider = get_bearer_token_provider(AzureKeyCredential(AZURE_OPENAISERVICE_KEY), "https://cognitiveservices.azure.com/.default")

        if OPENAI_HOST == "azure_custom":
            endpoint = os.environ["AZURE_OPENAI_CUSTOM_URL"]
        else:
            endpoint = f"https://{AZURE_OPENAI_SERVICE}.openai.azure.com"

        api_version = os.getenv("AZURE_OPENAI_API_VERSION") or "2024-03-01-preview"

        # openai_client = AsyncAzureOpenAI(
        #     api_version=api_version,
        #     azure_endpoint=endpoint,
        #     azure_ad_token_provider=token_provider,
        # )
        openai_client = AsyncAzureOpenAI(
            api_version=api_version,
            azure_endpoint=endpoint,
            api_key=AZURE_OPENAISERVICE_KEY,
        )
    elif OPENAI_HOST == "local":
        openai_client = AsyncOpenAI(
            base_url=os.environ["OPENAI_BASE_URL"],
            api_key="no-key-required",
        )
    else:
        openai_client = AsyncOpenAI(
            api_key=OPENAI_API_KEY,
            organization=OPENAI_ORGANIZATION,
        )

    current_app.config[CONFIG_OPENAI_CLIENT] = openai_client
    current_app.config[CONFIG_SEARCH_CLIENT] = search_client
    current_app.config[CONFIG_BLOB_CONTAINER_CLIENT] = blob_container_client
    current_app.config[CONFIG_AUTH_CLIENT] = auth_helper

    current_app.config[CONFIG_GPT4V_DEPLOYED] = bool(USE_GPT4V)
    current_app.config[CONFIG_SEMANTIC_RANKER_DEPLOYED] = AZURE_SEARCH_SEMANTIC_RANKER != "disabled"
    current_app.config[CONFIG_VECTOR_SEARCH_ENABLED] = os.getenv("USE_VECTORS", "").lower() != "false"
    current_app.config[CONFIG_USER_UPLOAD_ENABLED] = bool(USE_USER_UPLOAD)
    current_app.config[CONFIG_SHOW_THOUGHT_PROCESS] = os.getenv("SHOW_THOUGHT_PROCESS", "").lower() == "true"
    current_app.config[CONFIG_SHOW_SUPPORTING_CONTENT] = os.getenv("SHOW_SUPPORTING_CONTENT", "").lower() == "true"
    current_app.config[AZURE_STORAGE_CONTAINER_ORIGINAL_DOCUMENTS] = blob_container_original_documents_client

    # Various approaches to integrate GPT and external knowledge, most applications will use a single one of these patterns
    # or some derivative, here we include several for exploration purposes
    current_app.config[CONFIG_ASK_APPROACH] = RetrieveThenReadApproach(
        search_client=search_client,
        openai_client=openai_client,
        auth_helper=auth_helper,
        chatgpt_model=OPENAI_CHATGPT_MODEL,
        chatgpt_deployment=AZURE_OPENAI_CHATGPT_DEPLOYMENT,
        embedding_model=OPENAI_EMB_MODEL,
        embedding_deployment=AZURE_OPENAI_EMB_DEPLOYMENT,
        embedding_dimensions=OPENAI_EMB_DIMENSIONS,
        sourcepage_field=KB_FIELDS_SOURCEPAGE,
        content_field=KB_FIELDS_CONTENT,
        query_language=AZURE_SEARCH_QUERY_LANGUAGE,
        query_speller=AZURE_SEARCH_QUERY_SPELLER,
    )

    current_app.config[CONFIG_CHAT_APPROACH] = ChatReadRetrieveReadApproach(
        search_client=search_client,
        openai_client=openai_client,
        auth_helper=auth_helper,
        chatgpt_model=OPENAI_CHATGPT_MODEL,
        chatgpt_deployment=AZURE_OPENAI_CHATGPT_DEPLOYMENT,
        embedding_model=OPENAI_EMB_MODEL,
        embedding_deployment=AZURE_OPENAI_EMB_DEPLOYMENT,
        embedding_dimensions=OPENAI_EMB_DIMENSIONS,
        sourcepage_field=KB_FIELDS_SOURCEPAGE,
        content_field=KB_FIELDS_CONTENT,
        query_language=AZURE_SEARCH_QUERY_LANGUAGE,
        query_speller=AZURE_SEARCH_QUERY_SPELLER,
    )

    if USE_GPT4V:
        current_app.logger.info("USE_GPT4V is true, setting up GPT4V approach")
        if not AZURE_OPENAI_GPT4V_MODEL:
            raise ValueError("AZURE_OPENAI_GPT4V_MODEL must be set when USE_GPT4V is true")
        token_provider = get_bearer_token_provider(azure_credential, "https://cognitiveservices.azure.com/.default")

        current_app.config[CONFIG_ASK_VISION_APPROACH] = RetrieveThenReadVisionApproach(
            search_client=search_client,
            openai_client=openai_client,
            blob_container_client=blob_container_client,
            auth_helper=auth_helper,
            vision_endpoint=AZURE_VISION_ENDPOINT,
            vision_token_provider=token_provider,
            gpt4v_deployment=AZURE_OPENAI_GPT4V_DEPLOYMENT,
            gpt4v_model=AZURE_OPENAI_GPT4V_MODEL,
            embedding_model=OPENAI_EMB_MODEL,
            embedding_deployment=AZURE_OPENAI_EMB_DEPLOYMENT,
            embedding_dimensions=OPENAI_EMB_DIMENSIONS,
            sourcepage_field=KB_FIELDS_SOURCEPAGE,
            content_field=KB_FIELDS_CONTENT,
            query_language=AZURE_SEARCH_QUERY_LANGUAGE,
            query_speller=AZURE_SEARCH_QUERY_SPELLER,
        )

        current_app.config[CONFIG_CHAT_VISION_APPROACH] = ChatReadRetrieveReadVisionApproach(
            search_client=search_client,
            openai_client=openai_client,
            blob_container_client=blob_container_client,
            auth_helper=auth_helper,
            vision_endpoint=AZURE_VISION_ENDPOINT,
            vision_token_provider=token_provider,
            gpt4v_deployment=AZURE_OPENAI_GPT4V_DEPLOYMENT,
            gpt4v_model=AZURE_OPENAI_GPT4V_MODEL,
            embedding_model=OPENAI_EMB_MODEL,
            embedding_deployment=AZURE_OPENAI_EMB_DEPLOYMENT,
            embedding_dimensions=OPENAI_EMB_DIMENSIONS,
            sourcepage_field=KB_FIELDS_SOURCEPAGE,
            content_field=KB_FIELDS_CONTENT,
            query_language=AZURE_SEARCH_QUERY_LANGUAGE,
            query_speller=AZURE_SEARCH_QUERY_SPELLER,
        )


@bp.after_app_serving
async def close_clients():
    await current_app.config[CONFIG_SEARCH_CLIENT].close()
    await current_app.config[CONFIG_BLOB_CONTAINER_CLIENT].close()
    if current_app.config.get(CONFIG_USER_BLOB_CONTAINER_CLIENT):
        await current_app.config[CONFIG_USER_BLOB_CONTAINER_CLIENT].close()


def create_app():
    
    app = Quart(__name__)
    app.register_blueprint(bp)

    if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        os.environ["OTEL_SERVICE_NAME"] = "aiassistant"
        app_insights_connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")

        configure_azure_monitor(connection_string=app_insights_connection_string)
        # This tracks HTTP requests made by aiohttp:
        AioHttpClientInstrumentor().instrument()
        # This tracks HTTP requests made by httpx:
        HTTPXClientInstrumentor().instrument()
        # This tracks OpenAI SDK requests:
        OpenAIInstrumentor().instrument()
        # This middleware tracks app route requests:
        app.asgi_app = OpenTelemetryMiddleware(app.asgi_app)  # type: ignore[assignment]

    # Level should be one of https://docs.python.org/3/library/logging.html#logging-levels
    default_level = "INFO"  # In development, log more verbosely
    if os.getenv("WEBSITE_HOSTNAME"):  # In production, don't log as heavily
        default_level = "WARNING"
    
    if allowed_origin := os.getenv("ALLOWED_ORIGIN"):
        logging.info("CORS enabled for %s", allowed_origin)
        cors(app, allow_origin=allowed_origin, allow_methods=["GET", "POST"])
    return app
