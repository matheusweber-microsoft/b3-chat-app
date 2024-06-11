import { Stack, Pivot, PivotItem } from "@fluentui/react";

import styles from "./AnalysisPanel.module.css";

import { SupportingContent } from "../SupportingContent";
import { ChatAppResponse, ThemesResponse, getOriginalCitationFilePath } from "../../api";
import { AnalysisPanelTabs } from "./AnalysisPanelTabs";
import { ThoughtProcess } from "./ThoughtProcess";
import { MarkdownViewer } from "../MarkdownViewer";
import { useMsal } from "@azure/msal-react";
import { getHeaders } from "../../api";
import { useLogin, getToken } from "../../authConfig";
import { useState, useEffect } from "react";
import "./AnalysisPanel.css";

interface Props {
    className: string;
    activeTab: AnalysisPanelTabs;
    onActiveTabChanged: (tab: AnalysisPanelTabs) => void;
    activeCitation: string | undefined;
    citationHeight: string;
    answer: ChatAppResponse;
    showSupportingContent: boolean;
    showThoughtProcess: boolean;
    theme: ThemesResponse | null;
}

const pivotItemDisabledStyle = { disabled: true, style: { color: "grey" } };

export const AnalysisPanel = ({
    answer,
    activeTab,
    activeCitation,
    citationHeight,
    className,
    onActiveTabChanged,
    showSupportingContent,
    showThoughtProcess,
    theme
}: Props) => {
    const isDisabledThoughtProcessTab: boolean = !answer.choices[0].context.thoughts;
    const isDisabledSupportingContentTab: boolean = !answer.choices[0].context.data_points;
    const isDisabledCitationTab: boolean = !activeCitation;
    const [citation, setCitation] = useState("");
    const [subthemeName, setSubthemeName] = useState("");
    const [fileName, setFileName] = useState("");

    const client = useLogin ? useMsal().instance : undefined;

    function formatOriginalCitationPath(filePath: string | undefined) {
        if (!filePath) {
            return "#";
        }

        const fileExtension = filePath.split(".").pop();

        if (fileExtension === "pdf") {
            const basePath = filePath.split("file=")[1];

            const lastSlashIndex = basePath.lastIndexOf("/");
            const directoryPath = basePath.substring(0, lastSlashIndex);

            return getOriginalCitationFilePath(`${directoryPath}.pdf`);
        } else {
            const newFilePath = filePath.replace("content", "content-original");
            return newFilePath;
        }
        return "#";
    }

    const fetchCitation = async () => {
        const token = client ? await getToken(client) : undefined;
        if (activeCitation) {
            // Get hash from the URL as it may contain #page=N
            // which helps browser PDF renderer jump to correct page N
            const originalHash = activeCitation.indexOf("#") ? activeCitation.split("#")[1] : "";
            const response = await fetch(activeCitation, {
                method: "GET",
                headers: getHeaders(token)
            });
            const citationContent = await response.blob();
            let citationObjectUrl = URL.createObjectURL(citationContent);

            if (originalHash) {
                citationObjectUrl += "#" + originalHash;
            }
            setCitation(citationObjectUrl);

            const url = activeCitation;
            const parts = url.split("/");
            const subthemeId = parts[2];

            let fileName = parts[parts.length - 1];

            if (fileName.endsWith(".pdf")) {
                // Extract the page number from the file name
                const match = fileName.match(/-(\d+)\.pdf$/);
                if (match) {
                    const pageNumber = match[1];
                    // Remove the -number from the file name
                    fileName = fileName.replace(/-\d+\.pdf$/, ".pdf");
                    // Add #page=number to the end
                    fileName += `#page=${pageNumber}`;
                } else {
                    fileName = fileName.replace(/\.pdf$/, "");
                }
            }

            setFileName(fileName);

            theme?.subThemes.forEach(subTheme => {
                console.log(subTheme.subthemeId);
                if (subthemeId.includes(subTheme.subthemeId)) {
                    setSubthemeName(subTheme.subthemeName);
                    return;
                }
            });

            console.log(activeCitation);
            console.log(citationObjectUrl);
            console.log(theme);
            console.log(subthemeName);
        }
    };
    useEffect(() => {
        fetchCitation();
    }, []);

    const renderFileViewer = () => {
        if (!activeCitation) {
            return null;
        }

        const fileExtension = activeCitation.split(".").pop()?.toLowerCase();
        switch (fileExtension) {
            case "png":
                return <img src={citation} className={styles.citationImg} alt="Citation Image" />;
            case "md":
                return <MarkdownViewer src={activeCitation} />;
            case "pdf":
                return <iframe title="Citation" src={citation} width="100%" height={citationHeight} />;
            case "docx":
                return <iframe title="Citation" src={citation} width="100%" height={citationHeight} />;
        }
    };

    return (
        <Pivot
            className={className}
            selectedKey={activeTab}
            onLinkClick={pivotItem => pivotItem && onActiveTabChanged(pivotItem.props.itemKey! as AnalysisPanelTabs)}
        >
            {showThoughtProcess && (
                <PivotItem
                    itemKey={AnalysisPanelTabs.ThoughtProcessTab}
                    headerText="Processo de pensamento"
                    headerButtonProps={isDisabledThoughtProcessTab ? pivotItemDisabledStyle : undefined}
                >
                    <ThoughtProcess thoughts={answer.choices[0].context.thoughts || []} />
                </PivotItem>
            )}
            {showSupportingContent && (
                <PivotItem
                    itemKey={AnalysisPanelTabs.SupportingContentTab}
                    headerText="Conteúdo de apoio"
                    headerButtonProps={isDisabledSupportingContentTab ? pivotItemDisabledStyle : undefined}
                >
                    <SupportingContent supportingContent={answer.choices[0].context.data_points} />
                </PivotItem>
            )}
            <PivotItem
                itemKey={AnalysisPanelTabs.CitationTab}
                headerText="Citação"
                headerButtonProps={isDisabledCitationTab ? pivotItemDisabledStyle : undefined}
            >
                {subthemeName && (
                    <div className="breadcrumb-container">
                        <span className="breadcrumb-item">{theme?.themeName}</span>
                        <span className="breadcrumb-separator">-</span>
                        <span className="breadcrumb-item">{subthemeName}</span>
                        <span className="breadcrumb-separator">-</span>
                        <span className="breadcrumb-item active">{fileName}</span>
                    </div>
                )}

                {renderFileViewer()}
            </PivotItem>
        </Pivot>
    );
};
