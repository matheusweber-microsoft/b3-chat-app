import { Outlet, NavLink, Link } from "react-router-dom";

import styles from "./Layout.module.css";

import HomeIcon from "../../assets/home-header.svg";

import { useLogin } from "../../authConfig";

import { LoginButton } from "../../components/LoginButton";
import SideBar from "../../components/SideBar/SideBar";

const Layout = () => {
    return (
        <div className={styles.containerBox}>
            <SideBar />
            <div className={styles.layout}>
                <header className={styles.header}>
                    <div className={styles.headerContent}>
                        <img src={HomeIcon} alt="b3 logo" />
                        <p className={styles.logoTitle}>HOME</p>
                    </div>
                </header>
                <Outlet />
            </div>
        </div>
    );
};

export default Layout;
