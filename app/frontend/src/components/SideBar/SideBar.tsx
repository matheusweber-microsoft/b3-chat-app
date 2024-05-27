import styles from "./SideBar.module.css";
import B3Logo from "../../assets/B3-logo.svg";

export default function SideBar() {
    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <img alt="b3 logo" src={B3Logo} />
                <p className={styles.logoTitle}>B3 GPT</p>
            </div>
            <div className={styles.divider} />
            <div className={styles.menu}>
                <div className={styles.menuItem}>
                    <div className={styles.menuLink}></div>
                </div>
            </div>
        </div>
    );
}
