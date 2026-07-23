import React, { useState } from "react";
import { Sparkles, ArrowRight, HelpCircle, FileText, ChevronRight, Loader2 } from "lucide-react";
import { motion } from "motion/react";
import { HistoryItem } from "../types";

interface QuestionInputWorkspaceProps {
  item: HistoryItem;
  onAskQuestion: (text: string) => void;
  isLoading: boolean;
}

export default function QuestionInputWorkspace({
  item,
  onAskQuestion,
  isLoading
}: QuestionInputWorkspaceProps) {
  const [question, setQuestion] = useState("");

  const suggestedHashtags = (item.suggestedQuestions?.length
    ? item.suggestedQuestions
    : [
        "결제한 지 7일 이내인데 서비스 해지 시 전액 환불받을 수 있나요?",
        "약관에 개인정보를 제3자에게 제공한다는 조항이 있나요?",
        "중도 해지 시 위약금이나 수수료가 발생하나요?",
      ]).map((text, index) => ({ label: `추천 질문 ${index + 1}`, text }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || isLoading) return;
    onAskQuestion(question.trim());
  };

  const handleHashtagClick = (text: string) => {
    setQuestion(text);
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-[#eef7f2] relative overflow-y-auto w-full p-6 md:p-10 select-none">
      
      {/* Decorative Document Illustration at Bottom Right */}
      <div className="absolute right-6 bottom-6 opacity-40 pointer-events-none hidden lg:block max-w-[560px] z-0 select-none">
        <img
          alt="FinePrint Document Illustration"
          className="w-full h-auto object-contain"
          src="https://lh3.googleusercontent.com/aida-public/AB6AXuAYIS_L2yxWYTImVGQSWPpAV7aBmuxSy-ufjRI7MrrPAk4ZdxC7JtzkbOAE0mqJQr4XZFEYKeyE7cQ1X2Ml0LQ7o6_PXe_PfQwSh3yF12TjZpsxgd5mX6tuJ3Q_g1d3jGWSvX6wlP4KVIEz1g9U1lm_ZGAI4YS40SQkCRDr4wfcrQqaota-E_WA-cgR0_V-eD6gVVURIBGBN7R2ZKAEnvgoztDNNmMjQ3wKIIgvWpMnsTlZL6GsNUwUwuQze4tx1jSglA"
          referrerPolicy="no-referrer"
        />
      </div>

      {/* Top Breadcrumb Navigation */}
      <div className="flex items-center gap-2 text-xs md:text-sm text-on-surface-variant/60 mb-8 relative z-10">
        <div className="w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center">
          <FileText size={12} />
        </div>
        <span className="font-bold text-on-surface">{item.serviceName}</span>
        <ChevronRight size={14} className="text-on-surface-variant/40" />
        <span className="font-semibold text-primary">질문하기</span>
      </div>

      {/* Centered Main Question Input Card */}
      <div className="flex-1 flex items-center justify-center relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="bg-surface-white border border-primary/5 rounded-3xl p-6 md:p-10 max-w-3xl w-full shadow-xl flex flex-col gap-6"
        >
          {/* Card Title & Description */}
          <div className="text-center flex flex-col gap-2">
            <h2 className="text-xl md:text-3xl font-headline font-extrabold text-on-surface tracking-tight">
              약관에 대해 무엇이든 물어보세요
            </h2>
            <p className="text-xs md:text-sm text-on-surface-variant/70 leading-relaxed max-w-md mx-auto font-medium">
              환불, 해지, 개인정보 등 궁금한 점을 입력하면 AI가 약관을 분석하여 답변해드립니다.
            </p>
          </div>

          {/* Form and Question Box */}
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="border border-border-muted/80 bg-slate-50/50 hover:bg-slate-50/80 focus-within:bg-surface-white focus-within:border-primary focus-within:ring-1 focus-within:ring-primary rounded-2xl p-4 transition-all flex flex-col gap-2 shadow-inner">
              <textarea
                id="question-textarea"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                disabled={isLoading}
                rows={5}
                maxLength={1000}
                placeholder="예: '구독 해지 후에도 결제가 됐는데 환불 가능한가요?' 또는 '계정이 정지된 이유가 궁금해요.'"
                className="w-full bg-transparent border-none outline-none focus:ring-0 text-sm md:text-base text-on-surface placeholder-on-surface-variant/45 resize-none leading-relaxed"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit(e);
                  }
                }}
              />
              <div className="flex justify-end">
                <span className="text-[10px] md:text-xs text-on-surface-variant/40 font-semibold select-none">
                  {question.length} / 1,000자
                </span>
              </div>
            </div>

            {/* Suggested Hashtags Row */}
            <div className="flex flex-wrap gap-2 items-center">
              {suggestedHashtags.map((tag, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleHashtagClick(tag.text)}
                  className={`px-3 py-1.5 rounded-full text-xs font-bold border transition-all cursor-pointer hover:scale-102 active:scale-98 ${
                    question === tag.text
                      ? "bg-primary border-primary text-on-primary shadow-sm"
                      : "bg-surface-white border-border-muted text-on-surface-variant/80 hover:bg-slate-50 hover:border-primary/40"
                  }`}
                >
                  #{tag.label}
                </button>
              ))}
            </div>

            {/* Big Analyze Button */}
            <button
              id="btn-analyze-submit"
              type="submit"
              disabled={isLoading || !question.trim()}
              className={`w-full py-4 px-6 rounded-2xl flex items-center justify-center gap-2.5 font-bold text-sm md:text-base transition-all select-none shadow-md ${
                isLoading
                  ? "bg-[#2a6b38] text-white cursor-wait"
                  : question.trim()
                    ? "bg-primary text-on-primary hover:bg-primary/95 cursor-pointer hover:-translate-y-0.5 active:translate-y-0 active:scale-99"
                    : "bg-border-muted/60 text-on-surface-variant/40 cursor-not-allowed shadow-none"
              }`}
            >
              {isLoading ? (
                <>
                  <Loader2 size={18} className="animate-spin stroke-[3] text-white" />
                  <span>분석 중...</span>
                </>
              ) : (
                <>
                  <Sparkles size={18} className="animate-pulse" />
                  <span>분석하기</span>
                </>
              )}
            </button>
          </form>
        </motion.div>
      </div>

    </div>
  );
}
