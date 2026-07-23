import React, { useState, useRef, useEffect } from "react";
import { HistoryItem, QAItem } from "../types";
import { 
  Shield, CheckCircle, ChevronDown, ChevronUp, CheckSquare, Square, 
  Send, Sparkles, FileText, Clipboard, FileCheck, Mail, ArrowUp, Loader2
} from "lucide-react";
import { motion, AnimatePresence } from "motion/react";

interface AnalysisWorkspaceProps {
  item: HistoryItem;
  onToggleTodo: (qaId: string, todoId: string) => void;
  onAskQuestion: (text: string) => void;
  isChatLoading: boolean;
}

export default function AnalysisWorkspace({ 
  item, 
  onToggleTodo, 
  onAskQuestion, 
  isChatLoading 
}: AnalysisWorkspaceProps) {
  const [isOriginalTextOpen, setIsOriginalTextOpen] = useState(false);
  const [questionInput, setQuestionInput] = useState("");
  const [copied, setCopied] = useState(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Active QA item inside this service (default to the last or selected one)
  const activeQA = item.queries.find(q => q.id === item.selectedQAId) || item.queries[item.queries.length - 1];

  // Auto scroll to bottom when a new question is loaded
  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTo({
        top: scrollContainerRef.current.scrollHeight,
        behavior: "smooth"
      });
    }
  }, [item.queries.length, item.selectedQAId]);

  const handleSend = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!questionInput.trim() || isChatLoading) return;
    onAskQuestion(questionInput.trim());
    setQuestionInput("");
  };

  const handleCopyDraft = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Helper to resolve clean display title based on QA category
  const getIssueTitle = (category: string) => {
    switch (category) {
      case "refund": 
        return "Subscription Refund Issue";
      case "renewal": 
        return "Automatic Renewal Issue";
      case "privacy": 
        return "Privacy Protection & Data Issue";
      case "fees": 
        return "Hidden Fees & Penalty Issue";
      default: 
        return "Terms & Conditions Issue";
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#eef7f2] relative">
      
      {/* Scrollable Main Content Pane */}
      <div 
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto px-4 md:px-10 py-6 flex flex-col gap-6 pb-36"
      >
        
        {/* Breadcrumb Header */}
        <div className="flex items-center gap-2 text-xs md:text-sm text-on-surface-variant/60 select-none">
          <div className="w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center">
            <FileText size={12} />
          </div>
          <span className="font-bold text-on-surface">{item.serviceName}</span>
          <span className="text-on-surface-variant/40">&gt;</span>
          <span className="font-semibold text-primary truncate max-w-[200px]">
            {activeQA ? activeQA.question : "분석 대기 중"}
          </span>
        </div>

        <AnimatePresence mode="wait">
          {activeQA ? (
            <motion.div
              key={activeQA.id}
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -15 }}
              transition={{ duration: 0.3 }}
              className="flex flex-col gap-6 max-w-4xl w-full mx-auto"
            >
              
              {/* Primary Content Block: Issue Title & AI Easy 해설 */}
              <div className="bg-surface-white border border-border-muted/70 rounded-3xl p-6 md:p-8 shadow-sm flex flex-col gap-4 relative overflow-hidden">
                <div className="flex justify-between items-start gap-4">
                  <div>
                    <span className="px-2.5 py-1 bg-primary/10 text-primary rounded-lg text-[10px] md:text-xs font-bold uppercase tracking-wider mb-2 inline-block">
                      {activeQA.category.toUpperCase()}
                    </span>
                    <h3 className="text-xl md:text-2xl font-headline font-extrabold text-on-surface tracking-tight">
                      {getIssueTitle(activeQA.category)}
                    </h3>
                  </div>
                  
                  {/* Evidence Verified Badge */}
                  <span className="px-3 py-1 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full text-[10px] md:text-xs font-bold flex items-center gap-1.5 shrink-0 select-none">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    Evidence Verified
                  </span>
                </div>

                <p className="text-sm md:text-base text-on-surface-variant/90 leading-relaxed font-medium mt-1">
                  {activeQA.answer}
                </p>
              </div>

              {/* Card 2: Terms Evidence */}
              <div className="bg-surface-white border border-border-muted/70 rounded-3xl p-6 md:p-8 shadow-sm flex flex-col gap-4">
                <h4 className="text-sm md:text-base font-extrabold text-on-surface flex items-center gap-2 select-none">
                  <Shield size={16} className="text-primary" />
                  Terms Evidence
                </h4>
                
                <div className="bg-slate-50/50 border border-slate-100 rounded-2xl p-4 md:p-5 text-xs md:text-sm text-on-surface-variant font-medium leading-relaxed italic relative">
                  <span className="absolute left-2 top-1 text-3xl font-serif text-primary/20">“</span>
                  <p className="pl-4 pr-2">{activeQA.evidence}</p>
                  <span className="absolute right-3 bottom-0 text-3xl font-serif text-primary/20">”</span>
                </div>

                {/* Collapsible Original Text */}
                <div className="border-t border-border-muted/40 pt-3">
                  <button
                    id="btn-toggle-original"
                    onClick={() => setIsOriginalTextOpen(!isOriginalTextOpen)}
                    className="text-xs font-bold text-primary hover:text-primary/80 flex items-center gap-1 cursor-pointer transition-colors"
                  >
                    <span>Original Text</span>
                    {isOriginalTextOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </button>
                  
                  <AnimatePresence>
                    {isOriginalTextOpen && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden mt-3"
                      >
                        <div className="bg-[#1e293b] text-slate-200 rounded-xl p-4 text-xs font-mono leading-relaxed whitespace-pre-wrap break-all shadow-inner">
                          {activeQA.originalText}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </div>

              {/* Card 3: What This Means (AI 권리 해설 상세) */}
              <div className="bg-surface-white border border-border-muted/70 rounded-3xl p-6 md:p-8 shadow-sm flex flex-col gap-3">
                <h4 className="text-sm md:text-base font-extrabold text-on-surface flex items-center gap-2 select-none">
                  <Sparkles size={16} className="text-primary" />
                  What this means
                </h4>
                <p className="text-xs md:text-sm text-on-surface-variant/80 leading-relaxed font-semibold">
                  이 조항은 서비스 제공자가 사용자의 동의나 명시적 취소행위가 없는 한 이용기간 만료 후 등록된 결제수단으로 요금을 매회 자동 연장하여 청구한다는 것을 의미합니다. 갱신 거절을 기한 내에 진행하지 않으면 자동으로 약정이 재결제 및 연장될 위험이 있습니다.
                </p>
              </div>

              {/* Card 4: To-Do Action Plan */}
              <div className="bg-surface-white border border-border-muted/70 rounded-3xl p-6 md:p-8 shadow-sm flex flex-col gap-4">
                <h4 className="text-sm md:text-base font-extrabold text-on-surface flex items-center gap-2 select-none">
                  <CheckSquare size={16} className="text-primary" />
                  To-Do List (권리 보호 행동 강령)
                </h4>
                
                <div className="flex flex-col gap-2.5">
                  {activeQA.todo.map((todo) => (
                    <button
                      id={`todo-item-${todo.id}`}
                      key={todo.id}
                      onClick={() => onToggleTodo(activeQA.id, todo.id)}
                      className={`w-full text-left p-3.5 rounded-2xl border flex items-start gap-3 transition-all cursor-pointer ${
                        todo.checked
                          ? "bg-emerald-50/40 border-emerald-200/80 text-on-surface-variant/50"
                          : "bg-surface-white border-border-muted hover:border-primary/40 text-on-surface"
                      }`}
                    >
                      <span className="mt-0.5 flex-shrink-0 transition-transform duration-200 active:scale-75">
                        {todo.checked ? (
                          <CheckSquare size={17} className="text-primary fill-primary-container" />
                        ) : (
                          <Square size={17} className="text-on-surface-variant/40" />
                        )}
                      </span>
                      <span className={`text-xs md:text-sm font-bold ${todo.checked ? "line-through" : ""}`}>
                        {todo.text}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Card 5: Required Evidence Materials */}
              {activeQA.materials && activeQA.materials.length > 0 && (
                <div className="bg-surface-white border border-border-muted/70 rounded-3xl p-6 md:p-8 shadow-sm flex flex-col gap-3">
                  <h4 className="text-sm md:text-base font-extrabold text-on-surface flex items-center gap-2 select-none">
                    <FileCheck size={16} className="text-primary" />
                    필수 입증 준비 자료
                  </h4>
                  <ul className="space-y-2 pl-1">
                    {activeQA.materials.map((mat, idx) => (
                      <li key={idx} className="text-xs md:text-sm text-on-surface-variant flex items-center gap-2.5 font-bold">
                        <span className="w-2 h-2 rounded-full bg-primary shrink-0" />
                        <span>{mat}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Card 6: Customer Support Draft Mail */}
              {activeQA.draft && activeQA.draft.trim().length > 0 && (
                <div className="bg-surface-white border border-border-muted/70 rounded-3xl p-6 md:p-8 shadow-sm flex flex-col gap-4">
                  <div className="flex justify-between items-center border-b border-border-muted/30 pb-3">
                    <h4 className="text-sm md:text-base font-extrabold text-on-surface flex items-center gap-2 select-none">
                      <Mail size={16} className="text-primary" />
                      고객센터 공식 발송 이메일 초안
                    </h4>
                    
                    <button
                      id="btn-copy-draft-results"
                      onClick={() => handleCopyDraft(activeQA.draft!)}
                      className={`px-3 py-1.5 text-xs font-bold rounded-xl border transition-all flex items-center gap-1.5 cursor-pointer active:scale-95 ${
                        copied
                          ? "bg-emerald-50 border-emerald-300 text-emerald-700"
                          : "bg-surface-white border-border-muted hover:border-primary/50 text-on-surface"
                      }`}
                    >
                      <Clipboard size={13} />
                      {copied ? "복사 완료" : "초안 복사"}
                    </button>
                  </div>

                  <div className="bg-background-mint/20 border border-outline-variant/10 rounded-2xl p-4 text-xs md:text-sm font-mono text-on-surface-variant/90 leading-relaxed whitespace-pre-wrap break-all select-all">
                    {activeQA.draft}
                  </div>
                </div>
              )}

            </motion.div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center py-24 select-none">
              <Loader2 size={32} className="animate-spin text-primary mb-4" />
              <p className="text-sm text-on-surface-variant font-bold">약관 분석 가이드를 도출하는 중입니다...</p>
            </div>
          )}
        </AnimatePresence>

      </div>

      {/* Floating Centered Chat Input Panel at the very bottom (as circled in Red in Image 2) */}
      <div className="absolute bottom-0 left-0 right-0 p-4 md:p-6 bg-gradient-to-t from-[#eef7f2] via-[#eef7f2]/95 to-transparent z-40">
        <div className="max-w-3xl w-full mx-auto relative">
          <form 
            onSubmit={handleSend} 
            className="flex items-center gap-3 bg-surface-white border border-border-muted/80 rounded-full px-5 py-3 shadow-lg hover:border-primary/50 focus-within:border-primary/70 focus-within:ring-2 focus-within:ring-primary/10 transition-all"
          >
            <input
              id="followup-chat-input"
              type="text"
              value={questionInput}
              onChange={(e) => setQuestionInput(e.target.value)}
              disabled={isChatLoading}
              placeholder="Ask a follow-up question..."
              className="flex-1 bg-transparent border-none outline-none focus:ring-0 text-sm md:text-base text-on-surface placeholder-on-surface-variant/50 pr-2"
            />
            
            <button
              id="btn-submit-followup"
              type="submit"
              disabled={isChatLoading || !questionInput.trim()}
              className={`w-9 h-9 rounded-full flex items-center justify-center text-on-primary shrink-0 transition-all active:scale-90 ${
                isChatLoading
                  ? "bg-[#2a6b38] cursor-wait shadow-md"
                  : questionInput.trim()
                    ? "bg-primary hover:bg-primary/95 cursor-pointer shadow-md"
                    : "bg-outline-variant/30 cursor-not-allowed"
              }`}
            >
              {isChatLoading ? (
                <Loader2 size={18} className="animate-spin stroke-[3] text-white" />
              ) : (
                <ArrowUp size={18} className="stroke-[2.5]" />
              )}
            </button>
          </form>
        </div>
      </div>

    </div>
  );
}
