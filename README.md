# Introduction

The AI Assistant application is built using a standard client/server architecture. The Frontend application is a Javascript written using React and Typescript, the backend API is built using Python Quart framework. The purpose of this application is to allow B3 authorized users to chat with their data using various themes.
 
Please refer to the following section for more information on how to deploy the application

## Deploying the AI Assistant to AKS

The AI Assistant Application is deployed to one single container,the backend API and the Frontend UI are containerized into the same docker image. One single image needs to be created and pushed to Azure Container Registry before deploying it to AKS cluster.

To build the image and push it to ACR from a developer machine which has access to the code, we can do the following using PowerShell:

```PS
$ACR_NAME="azracrtechian"
$CHAT_APP_NAME="aiassistant"
$AKS_CLUSTER="azr-aks-tech-ia-n"

#Build and push the image
cd <local path>\ti-ea-chat-b3gpt\
az acr build --registry $ACR_NAME --image "$($CHAT_APP_NAME):latest" --file 'dockerfile' .
```

Once the image is built and pushed to ACR, we can deploy the image to a container using the `deployment` yaml files which exists in the directory `deploy`.

To deploy the AI Assistant application, you can run the below command:
```
kubectl apply -f "deploy/aiassistant-deployment.yml" -n copilotob3gpt
```

## Environment variables
The container relies on the following environment variables for its configuration:

- `MONGODB_CONN_STRING`: The MongoDB connection string, this value is obtained from Azure Key Vault as a secret reference using Container Storage Interface for secret stores.
- `AZURE_STORAGE_ACCOUNT_CONN_STRING`: The Azure Storage Account connection string, this value is obtained from Azure Key Vault as a secret reference using Container Storage Interface for secret stores.
- `APPLICATIONINSIGHTS_CONNECTION_STRING`: The Application Insights connection string, this value is obtained from Azure Key Vault as a secret reference using Container Storage Interface for secret stores.
- `CHATAPP_API_AZURE_CLIENT_SECRET`: The Client Secret of the application named `b3gpt-aiassistant-api` registered into Entra ID, this value is obtained from Azure Key Vault as a secret reference using Container Storage Interface for secret stores.
- `AZURE_SEARCH_SERVICE_QUERY_KEY`: The Azure Search Query API Key, this value is obtained from Azure Key Vault as a secret reference using Container Storage Interface for secret stores.
- `AZURE_OPENAISERVICE_KEY`: The Azure Open AI API Key, this value is obtained from Azure Key Vault as a secret reference using Container Storage Interface for secret stores.
- `DATABASE_NAME`: The MongoDB database name which themes are fetched from.
- `AZURE_OPENAI_CHATGPT_DEPLOYMENT`: The ChatGPT deployment name i.e. `gpt35-b3gptcopilot-principal`.
- `AZURE_OPENAI_CHATGPT_MODEL`: The ChatGPT deployment model i.e. `gpt-35-turbo-16k`.
- `AZURE_OPENAI_EMB_DEPLOYMENT`: The text embedding deployment name i.e. `text-embedding-b3gptcopilot-principal`.
- `AZURE_OPENAI_EMB_MODEL_NAME`: The text embedding deployment model i.e. `text-embedding-ada-002`.
- `AZURE_OPENAI_SERVICE`: The Azure OPEN AI Service name.
- `AZURE_SEARCH_INDEX`: The default Azure Search AI Index name. i.e. `manualsoperations-index-port`.
- `AZURE_SEARCH_SERVICE`: The Azure Search AI Service name.
- `AZURE_STORAGE_ACCOUNT`: The Azure Storage Account name.
- `AZURE_STORAGE_CONTAINER`: The Azure Storage Container name which stores the processed documents.
- `AZURE_SUBSCRIPTION_ID`: Azure Subscription ID.
- `AZURE_TENANT_ID`:  The Azure Tenant ID used for authentication Entra ID users.
- `AZURE_USE_AUTHENTICATION`: boolean flag to disable authentication, default value is `true`.
- `BACKEND_URI`: The backend URI for the chat API.
- `AZURE_AUTH_TENANT_ID`:  The Azure Tenant ID used for authentication Entra ID users.
- `AZURE_SERVER_APP_ID`: The Client ID of the application named `b3gpt-aiassistant-api` registered into Entra ID.
- `AZURE_CLIENT_APP_ID`: The Client ID of the application named `b3gpt-aiassistant-webapp` registered into Entra ID.
- `SHOW_SUPPORTING_CONTENT`: Boolean flag to show/hide supporting content feature, default value is `true`.
- `SHOW_THOUGHT_PROCESS`: Boolean flag to show/hide thought process feature, default value is `true`.
