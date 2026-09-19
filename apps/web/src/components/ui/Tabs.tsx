'use client';

import React, { createContext, useContext, useState } from 'react';
import styles from './Tabs.module.css';

interface TabsContextValue {
  activeTab: string;
  setActiveTab: (id: string) => void;
}

const TabsContext = createContext<TabsContextValue | null>(null);

export interface TabsProps extends React.HTMLAttributes<HTMLDivElement> {
  defaultValue: string;
  value?: string;
  onValueChange?: (value: string) => void;
}

export const Tabs: React.FC<TabsProps> = ({
  defaultValue,
  value,
  onValueChange,
  children,
  className = '',
  ...props
}) => {
  const [internalTab, setInternalTab] = useState(defaultValue);
  const activeTab = value !== undefined ? value : internalTab;

  const setActiveTab = (id: string) => {
    if (value === undefined) {
      setInternalTab(id);
    }
    onValueChange?.(id);
  };

  return (
    <TabsContext.Provider value={{ activeTab, setActiveTab }}>
      <div className={`${styles.tabsContainer} ${className}`} {...props}>
        {children}
      </div>
    </TabsContext.Provider>
  );
};

export const TabsList: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({
  children,
  className = '',
  ...props
}) => {
  return (
    <div className={`${styles.tabsList} ${className}`} role="tablist" {...props}>
      {children}
    </div>
  );
};

export interface TabTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  value: string;
  icon?: React.ReactNode;
  badge?: React.ReactNode;
}

export const TabTrigger: React.FC<TabTriggerProps> = ({
  value,
  icon,
  badge,
  children,
  className = '',
  ...props
}) => {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error('TabTrigger must be used within Tabs');

  const isActive = ctx.activeTab === value;

  return (
    <button
      role="tab"
      type="button"
      aria-selected={isActive}
      className={`${styles.tabTrigger} ${isActive ? styles.active : ''} ${className}`}
      onClick={() => ctx.setActiveTab(value)}
      {...props}
    >
      {icon && <span className={styles.tabIcon}>{icon}</span>}
      <span>{children}</span>
      {badge && <span className={styles.tabBadge}>{badge}</span>}
    </button>
  );
};

export interface TabContentProps extends React.HTMLAttributes<HTMLDivElement> {
  value: string;
}

export const TabContent: React.FC<TabContentProps> = ({
  value,
  children,
  className = '',
  ...props
}) => {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error('TabContent must be used within Tabs');

  if (ctx.activeTab !== value) return null;

  return (
    <div
      role="tabpanel"
      className={`${styles.tabContent} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
};
