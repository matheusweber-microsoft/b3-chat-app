import { Example } from "./Example";

import styles from "./Example.module.css";

const DEFAULT_EXAMPLES: string[] = [
    "What are the types of orders? aaaa",
    "What is the criteria for suspending trading in assets or derivatives?",
    "What are the procedures followed to ensure the functioning of the markers to mitigate systematic risks?"
];

const GPT4V_EXAMPLES: string[] = [
    "Compare the impact of interest rates and GDP in financial markets.",
    "What is the expected trend for the S&P 500 index over the next five years? Compare it to the past S&P 500 performance",
    "Can you identify any correlation between oil prices and stock market trends?"
];

interface Props {
    onExampleClicked: (value: string) => void;
    useGPT4V?: boolean;
    questions: string[];
}

export const ExampleList = ({ onExampleClicked, useGPT4V, questions }: Props) => {

    return (
        <ul className={styles.examplesNavList}>
            {questions.map((question: string, i: number) => (
                <li key={i}>
                    <Example text={question} value={question} onClick={onExampleClicked} />
                </li>
            ))}
        </ul>
    );
};
