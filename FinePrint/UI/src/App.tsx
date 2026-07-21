import React, { useState, useEffect } from "react";
import { 
  Menu, Plus, Settings, HelpCircle, ChevronLeft, ChevronRight, 
  Trash2, AlertTriangle, Sparkles, MessageSquare, CheckCircle, User,
  HelpCircle as HelpIcon, FileText, Loader2, Search, Globe, Check, Clock, LogOut,
  ChevronDown, ChevronUp
} from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { HistoryItem, QAItem, formatServiceName } from "./types";
import { mockHistoryItems } from "./mockData";
import HomeWorkspace from "./components/HomeWorkspace";
import AnalysisWorkspace from "./components/AnalysisWorkspace";
import QuestionInputWorkspace from "./components/QuestionInputWorkspace";
import MyAnalysisWorkspace from "./components/MyAnalysisWorkspace";
import AnalysisLoadingOverlay from "./components/AnalysisLoadingOverlay";
import { auth, loginWithGoogle, logout, onAuthStateChanged, User as FirebaseUser } from "./lib/firebase";

const STORAGE_KEY = "fineprint_history_v2";

export default function App() {
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [collapsedItems, setCollapsedItems] = useState<Record<string, boolean>>({});
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [analysisStage, setAnalysisStage] = useState<"idle" | "searching" | "analyzing" | "completed">("idle");
  const [analysisType, setAnalysisType] = useState<"name" | "url" | "document">("name");
  const [analyzingServiceName, setAnalyzingServiceName] = useState("");
  const [user, setUser] = useState<FirebaseUser | null>(null);
  const [userDropdownOpen, setUserDropdownOpen] = useState(false);

  // Subscribe to Firebase Authentication state changes
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (currentUser) => {
      setUser(currentUser);
    });
    return () => unsubscribe();
  }, []);

  // Load history from LocalStorage or seed with mock items on mount
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        setHistoryItems(JSON.parse(saved));
      } catch (e) {
        setHistoryItems(mockHistoryItems);
      }
    } else {
      setHistoryItems(mockHistoryItems);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(mockHistoryItems));
    }
  }, []);

  // Save history state changes helper
  const saveHistory = (updated: HistoryItem[]) => {
    setHistoryItems(updated);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  };

  // Registers a service, cleans name, and prepares suggestions (RAG Initial Registration)
  const handleAnalyze = async (type: "name" | "url" | "document", query: string) => {
    setIsLoading(true);
    setErrorMessage(null);
    setAnalysisType(type);
    
    // Determine friendly display name for progress indicator
    let displayName = query;
    if (type === "url") {
      displayName = query.replace(/https?:\/\/(www\.)?/, "").split("/")[0];
    } else if (type === "document") {
      // If document upload was used, we extracted a clean title if available, otherwise use a placeholder
      displayName = "업로드된 약관 문서";
    }
    setAnalyzingServiceName(displayName);
    setAnalysisStage("searching");

    try {
      // Simulate real-world search/crawl phase duration for high fidelity
      await new Promise((resolve) => setTimeout(resolve, 1200));

      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type, query })
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.error || "이용약관 분석 및 가이드 추출에 실패했습니다.");
      }

      const data = await response.json();

      // Transition to Analyzing phase
      setAnalysisStage("analyzing");
      await new Promise((resolve) => setTimeout(resolve, 1800));

      // Create a new empty HistoryItem for this service with suggested questions
      const newItem: HistoryItem = {
        id: `analysis-${Date.now()}`,
        serviceName: data.serviceName || displayName,
        type,
        query,
        date: new Date().toISOString().split("T")[0],
        queries: [], // Initial state is empty questions
        suggestedQuestions: data.suggestedQuestions || []
      };

      // Transition to Completed phase
      setAnalysisStage("completed");
      await new Promise((resolve) => setTimeout(resolve, 1500));

      const updatedHistory = [newItem, ...historyItems];
      saveHistory(updatedHistory);
      setSelectedItemId(newItem.id);
      setSuccessMessage(`${newItem.serviceName} 서비스 등록 완료!`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: any) {
      console.error(err);
      setErrorMessage(err.message || "서버 통신에 실패했습니다. API Key를 확인해 주세요.");
    } finally {
      setIsLoading(false);
      setAnalysisStage("idle");
    }
  };

  const handleGoogleLogin = async () => {
    try {
      const loggedInUser = await loginWithGoogle();
      setSuccessMessage(`${loggedInUser.displayName || "사용자"}님, 환영합니다!`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: any) {
      console.error(err);
      setErrorMessage("구글 로그인에 실패했습니다. 팝업 차단 여부 또는 설정을 확인해 주세요.");
      setTimeout(() => setErrorMessage(null), 4000);
    }
  };

  const handleGoogleLogout = async () => {
    try {
      await logout();
      setUserDropdownOpen(false);
      setSuccessMessage("정상적으로 로그아웃 되었습니다.");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: any) {
      console.error(err);
      setErrorMessage("로그아웃 처리 중 오류가 발생했습니다.");
      setTimeout(() => setErrorMessage(null), 3000);
    }
  };

  // Toggles single checklist items under specific questions
  const handleToggleTodo = (qaId: string, todoId: string) => {
    if (!selectedItemId) return;
    const updated = historyItems.map(item => {
      if (item.id === selectedItemId) {
        const updatedQueries = item.queries.map(q => {
          if (q.id === qaId) {
            return {
              ...q,
              todo: q.todo.map(t => t.id === todoId ? { ...t, checked: !t.checked } : t)
            };
          }
          return q;
        });
        return { ...item, queries: updatedQueries };
      }
      return item;
    });
    saveHistory(updated);
  };

  // RAG Deep Question Answering
  const handleAskQuestion = async (questionText: string) => {
    if (!selectedItemId) return;
    const activeItem = historyItems.find(item => item.id === selectedItemId);
    if (!activeItem) return;

    setIsChatLoading(true);
    setErrorMessage(null);

    const isFirstQuestion = activeItem.queries.length === 0;

    if (isFirstQuestion) {
      setAnalysisType(activeItem.type);
      setAnalyzingServiceName(activeItem.serviceName);
    }

    try {
      const response = await fetch("/api/question", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          serviceName: activeItem.serviceName,
          type: activeItem.type,
          originalQuery: activeItem.query,
          question: questionText
        })
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.error || "질문 처리에 오류가 발생했습니다.");
      }

      const data = await response.json();

      const newQA: QAItem = {
        id: `qa-${Date.now()}`,
        question: questionText,
        category: data.category || "other",
        answer: data.answer || "상세 설명을 도출할 수 없습니다.",
        evidence: data.evidence || "관련 근거 약관을 발췌할 수 없습니다.",
        originalText: data.originalText || "해당 원본 조항 전문이 제공되지 않습니다.",
        todo: (data.todo || []).map((todoText: string, tIdx: number) => ({
          id: `todo-${tIdx}-${Date.now()}`,
          text: todoText,
          checked: false
        })),
        materials: data.materials || [],
        draft: data.draft || "",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
      };

      const updatedHistory = historyItems.map(item => {
        if (item.id === selectedItemId) {
          const newQueries = [...item.queries, newQA];
          return {
            ...item,
            queries: newQueries,
            selectedQAId: newQA.id // Instantly focus on the newly analyzed question
          };
        }
        return item;
      });

      saveHistory(updatedHistory);
      setSuccessMessage("약관 RAG 분석이 완료되었습니다.");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: any) {
      console.error(err);
      setErrorMessage(err.message || "답변 분석에 실패했습니다. 우측 상단 Secrets 패널을 통해 API Key 상태를 확인해 주세요.");
    } finally {
      setIsChatLoading(false);
      setAnalysisStage("idle");
    }
  };

  // Delete service history item
  const handleDeleteHistory = (e: React.MouseEvent, itemId: string) => {
    e.stopPropagation();
    const updated = historyItems.filter(item => item.id !== itemId);
    saveHistory(updated);
    if (selectedItemId === itemId) {
      setSelectedItemId(null);
    }
  };

  // Delete a sub-question asked under a service
  const handleDeleteQuestion = (e: React.MouseEvent, itemId: string, qaId: string) => {
    e.stopPropagation();
    const updated = historyItems.map(item => {
      if (item.id === itemId) {
        const filteredQueries = item.queries.filter(q => q.id !== qaId);
        let nextSelectedQAId = item.selectedQAId;
        if (item.selectedQAId === qaId) {
          nextSelectedQAId = filteredQueries.length > 0 ? filteredQueries[0].id : undefined;
        }
        return {
          ...item,
          queries: filteredQueries,
          selectedQAId: nextSelectedQAId
        };
      }
      return item;
    });
    saveHistory(updated);
  };

  const activeItem = historyItems.find(item => item.id === selectedItemId);

  return (
    <div className="bg-background-mint h-screen flex text-on-surface font-sans overflow-hidden selection:bg-primary/20">
      
      {/* Toast Alert Banner */}
      <AnimatePresence>
        {errorMessage && (
          <motion.div
            initial={{ opacity: 0, y: -50 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -50 }}
            className="fixed top-4 left-1/2 -translate-x-1/2 z-[100] max-w-md w-full px-4"
          >
            <div className="bg-rose-50 border-2 border-rose-200 rounded-2xl p-4 shadow-xl flex items-start gap-3">
              <AlertTriangle className="text-rose-600 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-bold text-rose-800">오류 발생</p>
                <p className="text-xs text-rose-700 mt-1 leading-relaxed">{errorMessage}</p>
              </div>
              <button 
                onClick={() => setErrorMessage(null)} 
                className="text-rose-400 hover:text-rose-600 text-xs font-bold px-1.5 py-0.5 rounded-md cursor-pointer hover:bg-rose-100"
              >
                닫기
              </button>
            </div>
          </motion.div>
        )}
        
        {successMessage && (
          <motion.div
            initial={{ opacity: 0, y: -50 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -50 }}
            className="fixed top-4 left-1/2 -translate-x-1/2 z-[100] px-4"
          >
            <div className="bg-emerald-50 border-2 border-emerald-200 rounded-2xl py-3 px-5 shadow-xl flex items-center gap-2">
              <CheckCircle size={18} className="text-emerald-600 shrink-0" />
              <span className="text-sm font-bold text-emerald-800">{successMessage}</span>
            </div>
          </motion.div>
        )}

        {/* Dynamic Analysis multi-stage Loading Overlay */}
        {analysisStage !== "idle" && (
          <AnalysisLoadingOverlay
            stage={analysisStage}
            type={analysisType}
            serviceName={analyzingServiceName}
          />
        )}
      </AnimatePresence>

      {/* SideNavBar (Shared Component) */}
      <aside 
        id="main-sidebar"
        className={`fixed md:sticky top-0 left-0 h-screen bg-sidebar-bg border-r border-outline-variant/30 transition-all duration-300 z-[60] flex flex-col ${
          sidebarOpen ? "w-72" : "w-0 -translate-x-full md:translate-x-0 md:w-0"
        } overflow-hidden`}
      >
        <div className="p-5 flex flex-col h-full min-w-[18rem]">
          {/* Sidebar Header */}
          <div className="mb-6 flex justify-between items-start">
            <div>
              <h1 id="sidebar-logo" className="text-xl font-headline font-bold text-primary select-none cursor-pointer" onClick={() => setSelectedItemId(null)}>
                FinePrint
              </h1>
              <p className="text-[10px] text-on-surface-variant/70 font-semibold uppercase tracking-wider mt-0.5 select-none">
                AI Terms Q&A System
              </p>
            </div>
            
            {/* Toggle Button inside Sidebar */}
            <button 
              id="btn-sidebar-collapse"
              className="p-1 hover:bg-black/5 rounded-lg transition-colors text-on-surface-variant cursor-pointer" 
              onClick={() => setSidebarOpen(false)}
            >
              <ChevronLeft size={20} />
            </button>
          </div>

          {/* New Chat Button */}
          <button 
            id="btn-new-chat"
            onClick={() => setSelectedItemId(null)}
            className="mb-5 w-full bg-primary text-on-primary py-2.5 px-4 rounded-xl flex items-center justify-center gap-2 hover:bg-primary/95 transition-all active:scale-95 shadow-xs cursor-pointer group"
          >
            <Plus size={18} className="group-hover:rotate-90 transition-transform duration-200" />
            <span className="text-sm font-bold">새 서비스 분석</span>
          </button>

          {/* Sidebar History Items list (Hierarchical Service > Question Tree) */}
          <div className="flex-1 flex flex-col min-h-0">
            <p className="text-[10px] font-bold text-on-surface-variant/50 uppercase tracking-widest mb-2.5 select-none">
              분석 기록 히스토리 (서비스별)
            </p>
            <nav className="flex-1 space-y-2 overflow-y-auto pr-1">
              {historyItems.map((item) => {
                const isActive = item.id === selectedItemId;
                return (
                  <div key={item.id} className="flex flex-col">
                    {/* Service Block Head */}
                    <div
                      id={`history-item-${item.id}`}
                      onClick={() => {
                        setSelectedItemId(item.id);
                        // Auto focus on its first QA if available and none selected yet
                        if (item.queries.length > 0 && !item.selectedQAId) {
                          const updated = historyItems.map(hi => 
                            hi.id === item.id ? { ...hi, selectedQAId: hi.queries[0].id } : hi
                          );
                          saveHistory(updated);
                        }
                      }}
                      className={`group/item rounded-xl p-2.5 flex items-center justify-between gap-3 transition-all duration-200 cursor-pointer ${
                        isActive
                          ? "bg-primary-container text-on-primary-container font-bold shadow-xs border border-primary/10"
                          : "text-on-surface/85 hover:bg-black/5 hover:translate-x-1"
                      }`}
                    >
                      <div className="flex items-center gap-1.5 min-w-0 flex-1">
                        {item.queries.length > 0 && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setCollapsedItems(prev => ({
                                ...prev,
                                [item.id]: !prev[item.id]
                              }));
                            }}
                            className="p-1 hover:bg-black/5 rounded-md text-on-surface-variant/70 hover:text-primary transition-colors cursor-pointer shrink-0"
                            title={collapsedItems[item.id] ? "질문 펼치기" : "질문 접기"}
                          >
                            {collapsedItems[item.id] ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
                          </button>
                        )}
                        <FileText size={15} className={isActive ? "text-primary" : "text-on-surface-variant/50"} />
                        <span className="text-sm truncate font-semibold">
                          {formatServiceName(item.serviceName)}
                        </span>
                      </div>
                      
                      <button
                        id={`delete-history-${item.id}`}
                        onClick={(e) => handleDeleteHistory(e, item.id)}
                        className="opacity-0 group-hover/item:opacity-100 p-1 rounded-lg hover:bg-black/10 text-on-surface-variant hover:text-rose-600 transition-all cursor-pointer"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>

                    {/* Sub-list: Nested User Questions Asked under this Service */}
                    {item.queries.length > 0 && !collapsedItems[item.id] && (
                      <div className="pl-3.5 border-l border-outline-variant/30 ml-4.5 flex flex-col gap-1 mt-1.5 mb-2.5">
                        {item.queries.map((q) => {
                          const isQAActive = isActive && q.id === item.selectedQAId;
                          return (
                            <div
                              id={`qa-node-${q.id}`}
                              key={q.id}
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedItemId(item.id);
                                const updated = historyItems.map(hi => 
                                  hi.id === item.id ? { ...hi, selectedQAId: q.id } : hi
                                );
                                saveHistory(updated);
                              }}
                              className={`group/qa rounded-lg px-2.5 py-1.5 flex items-center justify-between gap-2 transition-all cursor-pointer text-xs ${
                                isQAActive
                                  ? "bg-primary/10 text-primary font-bold"
                                  : "text-on-surface-variant/70 hover:bg-black/5 hover:text-on-surface"
                              }`}
                            >
                              <span className="truncate pr-1">Q. {q.question}</span>
                              <button
                                id={`delete-qa-${q.id}`}
                                onClick={(e) => handleDeleteQuestion(e, item.id, q.id)}
                                className="opacity-0 group-hover/qa:opacity-100 p-0.5 rounded hover:bg-black/10 text-on-surface-variant/60 hover:text-rose-600 transition-all shrink-0 cursor-pointer"
                              >
                                <Trash2 size={11} />
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
              
              {historyItems.length === 0 && (
                <div className="text-center py-8 text-xs text-on-surface-variant/40 select-none">
                  등록된 서비스가 없습니다.
                </div>
              )}
            </nav>
          </div>

          {/* Sidebar footer utility layout */}
          <div className="mt-auto space-y-2 pt-5 border-t border-outline-variant/20">
            <div 
              id="sidebar-link-settings"
              onClick={() => {
                setErrorMessage("설정 및 API 비밀번호는 우측 상단의 AI Studio Secrets 패널을 통해 관리됩니다.");
                setTimeout(() => setErrorMessage(null), 4000);
              }}
              className="text-on-surface-variant/80 hover:bg-black/5 hover:text-on-surface p-2.5 rounded-lg flex items-center gap-3 transition-all cursor-pointer text-sm font-medium"
            >
              <Settings size={18} />
              <span>Settings</span>
            </div>
            <div 
              id="sidebar-link-help"
              onClick={() => {
                setSuccessMessage("사용법: 서비스를 등록한 후, 자동 결제 및 해지 환불 여부에 대해 자유롭게 질문해 보세요.");
                setTimeout(() => setSuccessMessage(null), 4000);
              }}
              className="text-on-surface-variant/80 hover:bg-black/5 hover:text-on-surface p-2.5 rounded-lg flex items-center gap-3 transition-all cursor-pointer text-sm font-medium"
            >
              <HelpCircle size={18} />
              <span>Help</span>
            </div>
          </div>
        </div>
      </aside>



      {/* Main Content Area */}
      <main className="flex-1 flex flex-col h-screen min-h-0 relative overflow-hidden transition-all duration-300">
        
        {/* TopAppBar (Shared Component) */}
        <header className="bg-primary-container text-on-primary-container flex justify-between items-center w-full px-6 md:px-10 h-14 z-50 shadow-xs border-b border-primary/10">
          <div className="flex items-center gap-3">
            {!sidebarOpen && (
              <button 
                id="btn-sidebar-toggle"
                className="p-1.5 hover:bg-primary/10 rounded-full transition-colors active:scale-95 cursor-pointer" 
                onClick={() => setSidebarOpen(true)}
              >
                <Menu size={20} />
              </button>
            )}
            <span 
              id="header-logo"
              className="text-lg md:text-xl font-headline font-bold cursor-pointer tracking-tight"
              onClick={() => setSelectedItemId(null)}
            >
              FinePrint
            </span>
          </div>
          
          <div className="flex items-center gap-6">
            <nav className="hidden md:flex items-center gap-6 h-full text-sm font-semibold">
              <button 
                id="nav-home"
                onClick={() => setSelectedItemId(null)} 
                className={`h-14 flex items-center px-1 border-b-2 transition-all cursor-pointer ${
                  selectedItemId === null 
                    ? "border-on-primary-container text-on-primary-container font-bold" 
                    : "border-transparent text-on-primary-container/70 hover:text-on-primary-container"
                }`}
              >
                Home
              </button>
              <button 
                id="nav-explore"
                onClick={() => {
                  setSuccessMessage("공유 가능한 공정 약관 목록(Explore) 서비스 준비 중입니다.");
                  setTimeout(() => setSuccessMessage(null), 3000);
                }}
                className="h-14 flex items-center px-1 border-b-2 border-transparent text-on-primary-container/70 hover:text-on-primary-container transition-all cursor-pointer"
              >
                Explore
              </button>
              <button 
                id="nav-my-analysis"
                onClick={() => setSelectedItemId("my-analysis")}
                className={`h-14 flex items-center px-1 border-b-2 transition-all cursor-pointer ${
                  selectedItemId === "my-analysis" 
                    ? "border-on-primary-container text-on-primary-container font-bold" 
                    : "border-transparent text-on-primary-container/70 hover:text-on-primary-container"
                }`}
              >
                My Analysis
              </button>
            </nav>
            
            {/* Elegant Login/User profile pill button with real Google OAuth */}
            <div className="relative">
              {user ? (
                <div className="flex items-center gap-2">
                  <button 
                    id="btn-user-profile"
                    onClick={() => setUserDropdownOpen(!userDropdownOpen)}
                    className="bg-surface-white text-on-surface border border-primary/10 pl-2 pr-4 py-1.5 rounded-full text-xs font-bold hover:bg-slate-50 transition-all active:scale-95 shadow-sm flex items-center gap-2 cursor-pointer"
                  >
                    {user.photoURL ? (
                      <img 
                        src={user.photoURL} 
                        alt="User Profile" 
                        referrerPolicy="no-referrer"
                        className="w-5 h-5 rounded-full object-cover shadow-inner"
                      />
                    ) : (
                      <div className="w-5 h-5 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-[10px]">
                        {user.displayName ? user.displayName[0] : "U"}
                      </div>
                    )}
                    <span className="truncate max-w-[100px]">{user.displayName || "사용자"}</span>
                  </button>

                  <AnimatePresence>
                    {userDropdownOpen && (
                      <>
                        {/* Invisible overlay backdrop for clicking outside to close */}
                        <div 
                          className="fixed inset-0 z-40 cursor-default" 
                          onClick={() => setUserDropdownOpen(false)} 
                        />
                        <motion.div
                          initial={{ opacity: 0, y: 10, scale: 0.95 }}
                          animate={{ opacity: 1, y: 0, scale: 1 }}
                          exit={{ opacity: 0, y: 10, scale: 0.95 }}
                          className="absolute right-0 mt-2.5 w-56 bg-surface-white border border-border-muted rounded-2xl p-4 shadow-xl z-50 flex flex-col gap-3.5"
                        >
                          <div className="flex flex-col gap-0.5">
                            <p className="text-xs font-bold text-on-surface">{user.displayName || "Google 사용자"}</p>
                            <p className="text-[10px] text-on-surface-variant/60 truncate font-semibold">{user.email}</p>
                          </div>
                          <hr className="border-border-muted/50 -mx-4" />
                          <button
                            id="btn-google-logout"
                            onClick={handleGoogleLogout}
                            className="w-full px-3 py-2 text-left hover:bg-rose-50 text-rose-600 hover:text-rose-700 rounded-xl text-xs font-bold flex items-center gap-2 transition-colors cursor-pointer"
                          >
                            <LogOut size={14} />
                            로그아웃
                          </button>
                        </motion.div>
                      </>
                    )}
                  </AnimatePresence>
                </div>
              ) : (
                <button 
                  id="btn-login-header"
                  onClick={handleGoogleLogin}
                  className="bg-primary text-on-primary border border-primary px-5 py-1.5 rounded-full text-xs font-bold hover:bg-primary/95 transition-all active:scale-95 shadow-sm flex items-center gap-1.5 cursor-pointer"
                >
                  <User size={13} className="stroke-[3]" />
                  <span>Google 로그인</span>
                </button>
              )}
            </div>
          </div>
        </header>

        {/* Dynamic Inner Workspace using AnimatePresence */}
        <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
          <AnimatePresence mode="wait">
            {activeItem ? (
              <div key={activeItem.id} className="flex-1 flex flex-col min-h-0">
                {activeItem.queries.length === 0 ? (
                  <QuestionInputWorkspace
                    item={activeItem}
                    onAskQuestion={handleAskQuestion}
                    isLoading={isChatLoading}
                  />
                ) : (
                  <AnalysisWorkspace
                    item={activeItem}
                    onToggleTodo={handleToggleTodo}
                    onAskQuestion={handleAskQuestion}
                    isChatLoading={isChatLoading}
                  />
                )}
              </div>
            ) : selectedItemId === "my-analysis" ? (
              <div key="my-analysis-workspace" className="flex-1 flex flex-col min-h-0">
                <MyAnalysisWorkspace
                  historyItems={historyItems}
                  onSelectItem={(itemId) => {
                    setSelectedItemId(itemId);
                    const item = historyItems.find(hi => hi.id === itemId);
                    if (item && item.queries.length > 0 && !item.selectedQAId) {
                      const updated = historyItems.map(hi => 
                        hi.id === item.id ? { ...hi, selectedQAId: hi.queries[0].id } : hi
                      );
                      saveHistory(updated);
                    }
                  }}
                  onDeleteItem={handleDeleteHistory}
                  onSelectQAItem={(itemId, qaId) => {
                    setSelectedItemId(itemId);
                    const updated = historyItems.map(hi => 
                      hi.id === itemId ? { ...hi, selectedQAId: qaId } : hi
                    );
                    saveHistory(updated);
                  }}
                  onGoToHome={() => setSelectedItemId(null)}
                />
              </div>
            ) : (
              <div key="home-workspace" className="flex-1 flex flex-col min-h-0">
                <HomeWorkspace
                  onAnalyze={handleAnalyze}
                  isLoading={isLoading}
                />
              </div>
            )}
          </AnimatePresence>
        </div>

        {/* Global Page Footer */}
        <footer className="mt-auto px-6 py-4 border-t border-outline-variant/15 w-full flex flex-col md:flex-row justify-between items-center bg-surface-white/20 text-[11px] text-on-surface-variant/70 gap-4 z-10 select-none">
          <div className="flex items-center gap-3">
            <span className="font-bold text-primary">FinePrint</span>
            <span>© 2026 FinePrint. Protective, clarifying, and empathetic legal AI.</span>
          </div>
          <div className="flex items-center gap-5 font-medium">
            <a href="#" className="hover:text-primary transition-colors">Terms of Service</a>
            <a href="#" className="hover:text-primary transition-colors">Privacy Policy</a>
            <a href="#" className="hover:text-primary transition-colors">Contact Support</a>
          </div>
        </footer>

      </main>
    </div>
  );
}
