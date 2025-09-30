import React, { useState, useCallback } from "react";
import { Edit2, Trash2, Check, Clock, AlertTriangle, Bell } from "lucide-react";

interface Alert {
  id: number;
  message: string;
  creationDate: string;
  creationTime: string;
}

interface TriggeredAlert extends Alert {
  triggeredDate: string;
  triggeredTime: string;
}

interface AcknowledgedAlert extends TriggeredAlert {
  acknowledgedDate: string;
  acknowledgedTime: string;
}

interface AlertCardProps {
  alert: Alert | TriggeredAlert | AcknowledgedAlert;
  type: "created" | "triggered" | "acknowledged";
  editingAlert: number | null;
  editMessage: string;
  setEditMessage: (message: string) => void;
  handleEdit: (alert: Alert) => void;
  saveEdit: (alertId: number) => void;
  cancelEdit: () => void;
  handleDelete: (alertId: number) => void;
  handleAcknowledge: (alert: TriggeredAlert) => void;
}

const AlertCard: React.FC<AlertCardProps> = React.memo(({
  alert,
  type,
  editingAlert,
  editMessage,
  setEditMessage,
  handleEdit,
  saveEdit,
  cancelEdit,
  handleDelete,
  handleAcknowledge,
}) => (
  <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-1 mb-2 hover:shadow-md transition-shadow duration-200">
    <div className="flex flex-col items-start justify-between">
      <div className="flex-1 w-full">
        {editingAlert === alert.id ? (
          <div className="space-y-2 text-xs">
            <textarea
              value={editMessage}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                setEditMessage(e.target.value)
              }
              className="w-full p-1 border border-gray-300 rounded-md resize-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              rows={2}
              autoFocus
            />
            <div className="flex space-x-2">
              <button
                onClick={() => saveEdit(alert.id)}
                className="px-1 py-0.5 bg-green-500 text-white rounded-md hover:bg-green-600 text-xs"
              >
                Save
              </button>
              <button
                onClick={cancelEdit}
                className="px-1 py-0.5 bg-gray-500 text-white rounded-md hover:bg-gray-600 text-xs"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <>
            <p className="text-muted-foreground text-[12px] font-medium mb-1">
              {alert.message}
            </p>
            <div className="space-y-1 mb-1">
              <div className="flex items-center text-[10px] text-gray-600">
                <Clock size={14} className="mr-1" />
                <span>
                  Created: {alert.creationDate} at {alert.creationTime}
                </span>
              </div>
              {(type === "triggered" || type === "acknowledged") &&
                "triggeredDate" in alert &&
                "triggeredTime" in alert && (
                  <div className="flex items-center text-[10px] text-orange-600">
                    <AlertTriangle size={14} className="mr-1" />
                    <span>
                      Triggered: {alert.triggeredDate} at {alert.triggeredTime}
                    </span>
                  </div>
                )}
              {type === "acknowledged" &&
                "acknowledgedDate" in alert &&
                "acknowledgedTime" in alert && (
                  <div className="flex items-center text-[10px] text-green-600">
                    <Check size={14} className="mr-1" />
                    <span>
                      Acknowledged: {alert.acknowledgedDate} at {alert.acknowledgedTime}
                    </span>
                  </div>
                )}
            </div>
          </>
        )}
      </div>

      {editingAlert !== alert.id && (
        <div className="flex self-end gap-2 mt-2">
          {type === "created" && (
            <>
              <button
                onClick={() => handleEdit(alert)}
                className="px-1 py-0.5 rounded-md text-blue-600 hover:bg-blue-100 transition-colors duration-200 flex items-center gap-1"
                title="Edit Alert"
              >
                <Edit2 size={12} />
              </button>
              <button
                onClick={() => handleDelete(alert.id)}
                className="px-1 py-0.5 rounded-md text-red-600 hover:bg-red-100 transition-colors duration-200 flex items-center gap-1"
                title="Delete Alert"
              >
                <Trash2 size={12} />
              </button>
            </>
          )}
          {type === "triggered" && (
            <button
              onClick={() => handleAcknowledge(alert as TriggeredAlert)}
              className="px-2 py-1 bg-blue-500 text-white rounded-md hover:bg-blue-600 text-[12px] flex items-center"
              title="Acknowledge Alert"
            >
              <Check size={14} className="mr-1" />
              Acknowledge
            </button>
          )}
        </div>
      )}
    </div>
  </div>
));

AlertCard.displayName = "AlertCard";

type TabType = "created" | "triggered" | "acknowledged";

const AlertManagementSystem: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>("created");
  
  const [createdAlerts, setCreatedAlerts] = useState<Alert[]>([
    {
      id: 1,
      message: "iPhone 15 Pro stock below minimum threshold",
      creationDate: "2025-09-26",
      creationTime: "10:30 AM",
    },
    {
      id: 2,
      message: "Samsung Galaxy S24 inventory running low",
      creationDate: "2025-09-26",
      creationTime: "11:15 AM",
    },
    {
      id: 3,
      message: "MacBook Air M3 requires immediate restocking",
      creationDate: "2025-09-25",
      creationTime: "03:45 PM",
    },
  ]);

  const [triggeredAlerts, setTriggeredAlerts] = useState<TriggeredAlert[]>([
    {
      id: 4,
      message: "iPad Pro 12.9 stock critically low",
      creationDate: "2025-09-25",
      creationTime: "02:20 PM",
      triggeredDate: "2025-09-26",
      triggeredTime: "09:15 AM",
    },
  ]);

  const [acknowledgedAlerts, setAcknowledgedAlerts] = useState<AcknowledgedAlert[]>([]);

  const [editingAlert, setEditingAlert] = useState<number | null>(null);
  const [editMessage, setEditMessage] = useState<string>("");

  // Handle edit alert
  const handleEdit = useCallback((alert: Alert): void => {
    setEditingAlert(alert.id);
    setEditMessage(alert.message);
  }, []);

  const saveEdit = useCallback(
    (alertId: number): void => {
      setCreatedAlerts((prev) =>
        prev.map((alert) =>
          alert.id === alertId ? { ...alert, message: editMessage } : alert
        )
      );
      setEditingAlert(null);
      setEditMessage("");
    },
    [editMessage]
  );

  const cancelEdit = useCallback((): void => {
    setEditingAlert(null);
    setEditMessage("");
  }, []);

  const handleDelete = useCallback((alertId: number): void => {
    setCreatedAlerts((prev) => prev.filter((alert) => alert.id !== alertId));
  }, []);

  const handleAcknowledge = useCallback((alert: TriggeredAlert): void => {
    const now = new Date();
    const acknowledgedAlert: AcknowledgedAlert = {
      ...alert,
      acknowledgedDate: now.toISOString().split("T")[0],
      acknowledgedTime: now.toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
      }),
    };

    setAcknowledgedAlerts((prev) => [...prev, acknowledgedAlert]);
    setTriggeredAlerts((prev) => prev.filter((a) => a.id !== alert.id));
  }, []);

  const tabs = [
    { id: "created" as TabType, label: "Created", count: createdAlerts.length, color: "blue" },
    { id: "triggered" as TabType, label: "Triggered", count: triggeredAlerts.length, color: "orange" },
    { id: "acknowledged" as TabType, label: "Acknowledged", count: acknowledgedAlerts.length, color: "green" },
  ];

  const renderAlerts = () => {
    switch (activeTab) {
      case "created":
        return createdAlerts.length > 0 ? (
          createdAlerts.map((alert) => (
            <AlertCard
              key={alert.id}
              alert={alert}
              type="created"
              editingAlert={editingAlert}
              editMessage={editMessage}
              setEditMessage={setEditMessage}
              handleEdit={handleEdit}
              saveEdit={saveEdit}
              cancelEdit={cancelEdit}
              handleDelete={handleDelete}
              handleAcknowledge={handleAcknowledge}
            />
          ))
        ) : (
          <div className="text-center py-8 text-gray-500">
            <Bell size={48} className="mx-auto mb-3 opacity-50" />
            <p className="text-sm">No created alerts</p>
          </div>
        );
      case "triggered":
        return triggeredAlerts.length > 0 ? (
          triggeredAlerts.map((alert) => (
            <AlertCard
              key={alert.id}
              alert={alert}
              type="triggered"
              editingAlert={editingAlert}
              editMessage={editMessage}
              setEditMessage={setEditMessage}
              handleEdit={handleEdit}
              saveEdit={saveEdit}
              cancelEdit={cancelEdit}
              handleDelete={handleDelete}
              handleAcknowledge={handleAcknowledge}
            />
          ))
        ) : (
          <div className="text-center py-8 text-gray-500">
            <AlertTriangle size={48} className="mx-auto mb-3 opacity-50" />
            <p className="text-sm">No triggered alerts</p>
          </div>
        );
      case "acknowledged":
        return acknowledgedAlerts.length > 0 ? (
          acknowledgedAlerts.map((alert) => (
            <AlertCard
              key={alert.id}
              alert={alert}
              type="acknowledged"
              editingAlert={editingAlert}
              editMessage={editMessage}
              setEditMessage={setEditMessage}
              handleEdit={handleEdit}
              saveEdit={saveEdit}
              cancelEdit={cancelEdit}
              handleDelete={handleDelete}
              handleAcknowledge={handleAcknowledge}
            />
          ))
        ) : (
          <div className="text-center py-8 text-gray-500">
            <Check size={48} className="mx-auto mb-3 opacity-50" />
            <p className="text-sm">No acknowledged alerts</p>
          </div>
        );
    }
  };

  return (
    <div className="p-4 h-auto">
      <h1 className="text-sm font-semibold text-foreground mb-5 text-start">
        Alerts
      </h1>

      <div className="bg-white rounded-xl shadow-lg p-2">
        {/* Tabs */}
        <div className="flex gap-1 mb-4 border-b border-gray-200 overflow-x-auto scrollbar-hidden">
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id;
            let activeClasses = "";
            let badgeClasses = "";
            
            if (isActive) {
              if (tab.id === "created") {
                activeClasses = "text-blue-600 border-b-2 border-blue-600";
                badgeClasses = "bg-blue-100 text-blue-800";
              } else if (tab.id === "triggered") {
                activeClasses = "text-orange-600 border-b-2 border-orange-600";
                badgeClasses = "bg-orange-100 text-orange-800";
              } else {
                activeClasses = "text-green-600 border-b-2 border-green-600";
                badgeClasses = "bg-green-100 text-green-800";
              }
            } else {
              activeClasses = "text-gray-500 hover:text-gray-700";
              badgeClasses = "bg-gray-100 text-gray-600";
            }
            
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`pb-2 px-1 text-xs transition-all duration-200 relative ${activeClasses}`}
              >
                <span className="flex items-center gap-1">
                  {tab.label}
                  <span className={`px-1 py-0.5 rounded-full text-[10px] ${badgeClasses}`}>
                    {tab.count}
                  </span>
                </span>
              </button>
            );
          })}
        </div>

        {/* Alerts Content */}
        <div className="max-h-[180px] overflow-y-auto pr-1 scrollbar-hidden">
          {renderAlerts()}
        </div>
      </div>

      {/* Add New Alert Button - Only show on created tab */}
      {activeTab === "created" && (
        <div className="fixed bottom-6 right-6">
          <button
            onClick={() => {
              const newAlert: Alert = {
                id: Date.now(),
                message: "New alert message",
                creationDate: new Date().toISOString().split("T")[0],
                creationTime: new Date().toLocaleTimeString("en-US", {
                  hour: "2-digit",
                  minute: "2-digit",
                  hour12: true,
                }),
              };
              setCreatedAlerts([newAlert, ...createdAlerts]);
            }}
            className="bg-blue-500 hover:bg-blue-600 text-white p-3 rounded-full shadow-lg transition-colors duration-200"
            title="Add New Alert"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 4v16m8-8H4"
              />
            </svg>
          </button>
        </div>
      )}
    </div>
  );
};

export default AlertManagementSystem;