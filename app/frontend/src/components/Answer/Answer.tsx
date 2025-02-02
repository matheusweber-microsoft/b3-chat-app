import { useMemo } from "react";
import { Stack, IconButton } from "@fluentui/react";
import DOMPurify from "dompurify";

import styles from "./Answer.module.css";

import { ChatAppResponse, getCitationFilePath } from "../../api";
import { parseAnswerToHtml } from "./AnswerParser";
import { AnswerIcon } from "./AnswerIcon";

interface Props {
    answer: ChatAppResponse;
    isSelected?: boolean;
    isStreaming: boolean;
    onCitationClicked: (filePath: string) => void;
    onThoughtProcessClicked: () => void;
    onSupportingContentClicked: () => void;
    onFollowupQuestionClicked?: (question: string) => void;
    showFollowupQuestions?: boolean;
    showSupportingContent: boolean;
    showThoughtProcess: boolean;
}

export const Answer = ({
    answer,
    isSelected,
    isStreaming,
    onCitationClicked,
    onThoughtProcessClicked,
    onSupportingContentClicked,
    onFollowupQuestionClicked,
    showFollowupQuestions,
    showSupportingContent,
    showThoughtProcess
}: Props) => {
    const followupQuestions = answer.choices[0].context.followup_questions;
    const messageContent = answer.choices[0].message.content;
    const parsedAnswer = useMemo(() => parseAnswerToHtml(messageContent, isStreaming, onCitationClicked), [answer]);

    const sanitizedAnswerHtml = DOMPurify.sanitize(parsedAnswer.answerHtml);

    const formatCitationTitle = (path: string) => {
        let parts = path.split("/");

        let lastPart = parts[parts.length - 1];

        return lastPart;
    };

    return (
        <Stack className={`${styles.answerContainer} ${isSelected && styles.selected}`} verticalAlign="space-between">
            <Stack.Item>
                <Stack horizontal horizontalAlign="space-between">
                    <AnswerIcon />
                    <div>
                        {showThoughtProcess && <IconButton
                            style={{ color: "black" }}
                            iconProps={{ iconName: "Lightbulb" }}
                            title="Mostrar processo de pensamento"
                            ariaLabel="Mostrar processo de pensamento"
                            onClick={() => onThoughtProcessClicked()}
                            disabled={!answer.choices[0].context.thoughts?.length}
                        />}
                        
                        {showSupportingContent && <IconButton
                            style={{ color: "black" }}
                            iconProps={{ iconName: "ClipboardList" }}
                            title="Mostrar conteúdo de apoio"
                            ariaLabel="Mostrar conteúdo de apoio"
                            onClick={() => onSupportingContentClicked()}
                            disabled={!answer.choices[0].context.data_points}
                        />}
                    </div>
                </Stack>
            </Stack.Item>

            <Stack.Item grow>
                <div className={styles.answerText} dangerouslySetInnerHTML={{ __html: sanitizedAnswerHtml }}></div>
            </Stack.Item>

            {!!parsedAnswer.citations.length && (
                <><Stack.Item>
                    <span className={styles.answerText}  style={{ color: "#6c757d" }}
 >
                        *Essa resposta foi gerada por um modelo de IA e pode está incorreta. É recomendado que você verifique as fontes.<br></br>
                    </span>
                </Stack.Item>
                <Stack.Item>
                        <Stack horizontal wrap tokens={{ childrenGap: 5 }}>
                            <span className={styles.citationLearnMore}>Citações:</span>
                            {parsedAnswer.citations.map((x, i) => {
                                const path = getCitationFilePath(x);
                                return (
                                    <a key={i} className={styles.citation} title={x} onClick={() => onCitationClicked(path)}>
                                        {`${++i}. ${formatCitationTitle(x)}`}
                                    </a>
                                );
                            })}
                        </Stack>
                    </Stack.Item></>
            )}

            {!!followupQuestions?.length && showFollowupQuestions && onFollowupQuestionClicked && (
                <Stack.Item>
                    <Stack horizontal wrap className={`${!!parsedAnswer.citations.length ? styles.followupQuestionsList : ""}`} tokens={{ childrenGap: 6 }}>
                        <span className={styles.followupQuestionLearnMore}>Follow-up questions:</span>
                        {followupQuestions.map((x, i) => {
                            return (
                                <a key={i} className={styles.followupQuestion} title={x} onClick={() => onFollowupQuestionClicked(x)}>
                                    {`${x}`}
                                </a>
                            );
                        })}
                    </Stack>
                </Stack.Item>
            )}
        </Stack>
    );
};
