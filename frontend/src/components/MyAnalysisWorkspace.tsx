import React, { useState } from "react";
import { motion } from "motion/react";
import { 
  Search, Trash2, Sparkles, Globe, FileText, ChevronRight, 
  Calendar, MessageSquare, AlertTriangle, Play, HelpCircle, CheckCircle, BarChart2,
  ChevronDown, ChevronUp
} from "lucide-react";
import { HistoryItem, formatServiceName } from "../types";

interface MyAnalysisWorkspaceProps {
  historyItems: HistoryItem[];
  onSelectItem: (itemId: string) => void;
  onDeleteItem: (e: React.MouseEvent, itemId: string) => void;
  onSelectQAItem: (itemId: string, qaId: string) => void;
  onGoToHome: () => void;
}

export default function MyAnalysisWorkspace({
  historyItems,
  onSelectItem,
  onDeleteItem,
  onSelectQAItem,
  onGoToHome
}: MyAnalysisWorkspaceProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedType, setSelectedType] = useState<"all" | "name" | "url" | "document">("all");
  const [collapsedItems, setCollapsedItems] = useState<Record<string, boolean>>({});

  // Calculate statistics
  const totalAnalyzed = historyItems.length;
  const totalQuestions = historyItems.reduce((acc, item) => acc + item.queries.length, 0);
  
  // Find the service with the most questions
  const mostActiveService = [...historyItems].sort((a, b) => b.queries.length - a.queries.length)[0];

  // Filter history items based on search query and type filter
  const filteredItems = historyItems.filter((item) => {
    const matchesSearch = item.serviceName.toLowerCase().includes(searchTerm.toLowerCase()) || 
      (item.query && item.query.toLowerCase().includes(searchTerm.toLowerCase()));
    
    const matchesType = selectedType === "all" || item.type === selectedType;
    
    return matchesSearch && matchesType;
  });

  return (
    <motion.div 
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -15 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className="flex-1 flex flex-col bg-[#eef7f2] relative overflow-y-auto w-full h-full p-6 md:p-10 select-none"
    >
      {/* Upper Title Section */}
      <div className="max-w-6xl w-full mx-auto mb-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-primary/10 pb-6">
          <div>
            <h1 className="text-2xl md:text-3xl font-headline font-bold text-on-surface tracking-tight flex items-center gap-2">
              <BarChart2 className="text-primary w-7 h-7" />
              나의 약관 분석 리포트
            </h1>
            <p className="text-sm text-on-surface-variant mt-1.5 leading-relaxed font-sans">
              FinePrint AI를 통해 심층 분석된 서비스 약관 및 문제 해결 질문 히스토리의 전체 목록입니다.
            </p>
          </div>
          <button
            onClick={onGoToHome}
            className="self-start md:self-auto bg-primary text-on-primary font-semibold text-xs px-4 py-2.5 rounded-xl hover:bg-primary/95 transition-all active:scale-95 shadow-xs flex items-center gap-1.5 cursor-pointer"
          >
            <Sparkles size={14} />
            새로운 약관 분석하기
          </button>
        </div>
      </div>

      {/* Main Content Dashboard Container */}
      <div className="max-w-6xl w-full mx-auto grid grid-cols-1 lg:grid-cols-4 gap-8">
        
        {/* Left Side: Stats and Filter Controls */}
        <div className="lg:col-span-1 flex flex-col gap-6">
          
          {/* Quick Stats Widget */}
          <div className="bg-surface-white border border-outline-variant/30 rounded-2xl p-5 shadow-xs">
            <h3 className="text-xs font-bold text-on-surface-variant/70 uppercase tracking-wider mb-4 flex items-center gap-1.5">
              <CheckCircle size={14} className="text-primary" />
              분석 활동 요약
            </h3>
            
            <div className="space-y-4">
              <div className="flex items-center justify-between border-b border-black/5 pb-3">
                <span className="text-xs text-on-surface-variant font-medium">총 분석 서비스</span>
                <span className="text-lg font-bold text-on-surface">{totalAnalyzed}개</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-on-surface-variant font-medium">총 누적 질문</span>
                <span className="text-lg font-bold text-primary">{totalQuestions}회</span>
              </div>
            </div>
          </div>

          {/* Quick Category Filters */}
          <div className="bg-surface-white border border-outline-variant/30 rounded-2xl p-5 shadow-xs">
            <h3 className="text-xs font-bold text-on-surface-variant/70 uppercase tracking-wider mb-3">
              분석 종류별 필터
            </h3>
            <div className="flex flex-col gap-1.5">
              {[
                { id: "all", label: "전체 분석 기록", icon: BarChart2, count: historyItems.length },
                { id: "name", label: "서비스명 검색", icon: Sparkles, count: historyItems.filter(i => i.type === "name").length },
                { id: "url", label: "웹 URL 입력", icon: Globe, count: historyItems.filter(i => i.type === "url").length },
                { id: "document", label: "문서 파일 업로드", icon: FileText, count: historyItems.filter(i => i.type === "document").length },
              ].map((tab) => {
                const isActive = selectedType === tab.id;
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setSelectedType(tab.id as any)}
                    className={`w-full text-left px-3 py-2.5 rounded-xl text-xs font-semibold flex items-center justify-between transition-all cursor-pointer ${
                      isActive 
                        ? "bg-primary text-on-primary font-bold shadow-xs" 
                        : "text-on-surface/80 hover:bg-black/5"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Icon size={14} className={isActive ? "text-on-primary" : "text-on-surface-variant/70"} />
                      <span>{tab.label}</span>
                    </div>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${
                      isActive ? "bg-on-primary/20 text-on-primary" : "bg-black/5 text-on-surface-variant/70"
                    }`}>
                      {tab.count}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

        </div>

        {/* Right Side: Search Input and List of Services */}
        <div className="lg:col-span-3 flex flex-col gap-4">
          
          {/* Search Box */}
          <div className="relative w-full">
            <div className="absolute inset-y-0 left-4 flex items-center pointer-events-none text-on-surface-variant/50">
              <Search size={18} />
            </div>
            <input
              type="text"
              placeholder="분석한 서비스 이름 또는 키워드를 검색하세요..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-surface-white border border-outline-variant/40 focus:border-primary/50 rounded-2xl py-3.5 pl-12 pr-4 text-sm font-medium shadow-xs focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all text-on-surface placeholder-on-surface-variant/40"
            />
          </div>

          {/* List of Analysis Records */}
          <div className="space-y-4">
            {filteredItems.length > 0 ? (
              filteredItems.map((item) => {
                // Get display icon based on type
                let TypeIcon = Sparkles;
                let typeColor = "bg-emerald-50 text-emerald-700 border-emerald-150";
                let typeLabel = "서비스명 분석";
                if (item.type === "url") {
                  TypeIcon = Globe;
                  typeColor = "bg-blue-50 text-blue-700 border-blue-150";
                  typeLabel = "URL 주소 분석";
                } else if (item.type === "document") {
                  TypeIcon = FileText;
                  typeColor = "bg-amber-50 text-amber-700 border-amber-150";
                  typeLabel = "약관 파일 분석";
                }

                return (
                  <motion.div
                    key={item.id}
                    layoutId={`analysis-card-${item.id}`}
                    className="bg-surface-white border border-outline-variant/30 rounded-2xl p-5 shadow-xs hover:shadow-md hover:border-primary/20 transition-all group/card flex flex-col md:flex-row justify-between items-start md:items-center gap-4"
                  >
                    {/* Left: Info & Title */}
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2 mb-2">
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${typeColor}`}>
                          {typeLabel}
                        </span>
                        <div className="flex items-center gap-1 text-[11px] text-on-surface-variant/60 font-medium">
                          <Calendar size={11} />
                          <span>{item.date}</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2.5 flex-wrap">
                        <h2 
                          onClick={() => onSelectItem(item.id)}
                          className="text-lg font-bold text-on-surface hover:text-primary transition-colors cursor-pointer inline-flex items-center gap-1.5 group-hover/card:translate-x-0.5 duration-150"
                        >
                          {formatServiceName(item.serviceName)}
                          <ChevronRight size={16} className="text-on-surface-variant/40 group-hover/card:text-primary transition-colors animate-pulse" />
                        </h2>

                        {item.queries.length > 0 && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setCollapsedItems(prev => ({
                                ...prev,
                                [item.id]: !prev[item.id]
                              }));
                            }}
                            className="px-2 py-0.5 text-[10px] font-bold text-on-surface-variant/70 hover:text-primary bg-black/5 hover:bg-primary/10 rounded-lg transition-all flex items-center gap-1 cursor-pointer select-none"
                            title={collapsedItems[item.id] ? "질문 목록 펼치기" : "질문 목록 접기"}
                          >
                            {collapsedItems[item.id] ? (
                              <>
                                <ChevronDown size={11} />
                                <span>질문 펼치기 ({item.queries.length})</span>
                              </>
                            ) : (
                              <>
                                <ChevronUp size={11} />
                                <span>접기</span>
                              </>
                            )}
                          </button>
                        )}
                      </div>

                      {/* Display analysis query source */}
                      <div className="mt-1">
                        <p className="text-xs text-on-surface-variant/75 font-mono truncate max-w-md bg-black/5 px-2 py-1 rounded-md inline-block">
                          {item.type === "url" ? item.query : (item.type === "document" ? "업로드된 PDF/TXT 문서" : `검색어: "${item.query}"`)}
                        </p>
                      </div>

                      {/* Sub-questions Preview list */}
                      {item.queries.length > 0 ? (
                        !collapsedItems[item.id] && (
                          <div className="mt-4 pt-3.5 border-t border-black/5">
                            <span className="text-[11px] font-bold text-on-surface-variant/60 uppercase block mb-2">
                              진행된 Q&A 질문 히스토리 ({item.queries.length}개)
                            </span>
                            <div className="flex flex-col gap-1.5">
                              {item.queries.map((q) => (
                                <button
                                  key={q.id}
                                  onClick={() => onSelectQAItem(item.id, q.id)}
                                  className="text-left w-full px-3 py-1.5 bg-background-mint/20 hover:bg-background-mint/50 border border-primary/5 rounded-xl flex items-center justify-between text-xs transition-all duration-150 cursor-pointer"
                                >
                                  <span className="font-semibold text-on-surface truncate pr-2 flex items-center gap-1.5">
                                    <MessageSquare size={12} className="text-primary shrink-0" />
                                    {q.question}
                                  </span>
                                  <span className="text-[10px] text-primary font-bold shrink-0 flex items-center gap-0.5">
                                    답변 확인
                                    <ChevronRight size={10} />
                                  </span>
                                </button>
                              ))}
                            </div>
                          </div>
                        )
                      ) : (
                        <div className="mt-3 text-xs text-on-surface-variant/50 italic flex items-center gap-1.5">
                          <HelpCircle size={13} className="text-on-surface-variant/40" />
                          <span>아직 질문이 없습니다. 궁금한 조항을 클릭하여 질문을 시작해 보세요.</span>
                        </div>
                      )}
                    </div>

                    {/* Right: Actions */}
                    <div className="flex md:flex-col items-center md:items-end justify-between w-full md:w-auto gap-3 shrink-0 pt-3 md:pt-0 border-t md:border-t-0 border-black/5">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => onSelectItem(item.id)}
                          className="bg-primary/10 hover:bg-primary/15 text-primary font-bold text-xs px-4 py-2.5 rounded-xl transition-all active:scale-95 flex items-center gap-1.5 cursor-pointer"
                        >
                          <Play size={12} className="fill-current" />
                          분석 이어하기
                        </button>
                        
                        <button
                          onClick={(e) => onDeleteItem(e, item.id)}
                          title="분석 기록 삭제"
                          className="p-2.5 bg-rose-50 hover:bg-rose-100 text-rose-600 rounded-xl transition-all active:scale-95 cursor-pointer flex items-center justify-center border border-rose-100"
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </div>

                  </motion.div>
                );
              })
            ) : (
              /* No matching search results */
              <div className="bg-surface-white border border-outline-variant/30 rounded-2xl py-12 px-6 text-center shadow-xs flex flex-col items-center">
                <AlertTriangle className="text-on-surface-variant/30 mb-3 w-10 h-10" />
                <h3 className="text-sm font-bold text-on-surface">검색 결과가 없습니다</h3>
                <p className="text-xs text-on-surface-variant/60 mt-1 max-w-xs">
                  다른 검색어를 입력하시거나, 필터 기준을 확인해 보세요.
                </p>
                <button
                  onClick={() => {
                    setSearchTerm("");
                    setSelectedType("all");
                  }}
                  className="mt-4 text-xs font-bold text-primary hover:underline cursor-pointer"
                >
                  필터 초기화
                </button>
              </div>
            )}
          </div>

        </div>

      </div>
    </motion.div>
  );
}
