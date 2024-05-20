import { Stack, IDropdownOption, Dropdown } from "@fluentui/react";

import styles from "./ThemeSettings.module.css";
import { ThemesResponse } from "../../api";

interface Props {
    theme: string;
    themes: ThemesResponse[];
    updateTheme: (themeId: string) => void;
}

export const ThemeSettings = ({ updateTheme, theme, themes }: Props) => {
    const onUpdateTheme = (_ev: React.FormEvent<HTMLDivElement>, option?: IDropdownOption<ThemesResponse> | undefined) => {
        updateTheme(option?.data ? option.data.themeId : "");
    };

    return (
        <Stack className={styles.container} tokens={{ childrenGap: 10 }}>
            <Dropdown
                label="Theme options"
                options={themes.map(th => ({ key: th.themeId, text: th.themeName, selected: th.themeId === theme, data: th }))}
                required
                onChange={onUpdateTheme}
            />
        </Stack>
    );
};
