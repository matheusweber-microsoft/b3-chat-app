import { Outlet, NavLink, Link } from "react-router-dom";

import styles from "./Layout.module.css";

import HomeIcon from "../../assets/home-header.svg";

import { useLogin } from "../../authConfig";

import { LoginButton } from "../../components/LoginButton";
import SideBar from "../../components/SideBar/SideBar";
import { AuthenticatedTemplate, UnauthenticatedTemplate, useMsal } from "@azure/msal-react";

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
                    <div className="flex items-center">
                        <LoginButton />
                    </div>
                </header>
                <AuthenticatedTemplate>
                    <Outlet />
                </AuthenticatedTemplate>
            </div>
            
        </div>
    );
};

export default Layout;
