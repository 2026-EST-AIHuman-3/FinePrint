import React from "react";
import { motion } from "motion/react";
import { 
  Loader2, Search, Globe, FileText, Check, Sparkles, ShieldCheck 
} from "lucide-react";

interface AnalysisLoadingOverlayProps {
  stage: "idle" | "searching" | "analyzing" | "completed";
  type: "name" | "url" | "document";
  serviceName: string;
}

export default function AnalysisLoadingOverlay({ 
  stage, 
  type, 
  serviceName 
}: AnalysisLoadingOverlayProps) {
  if (stage === "idle") return null;

  // Resolve descriptions based on submission types
  const getStepOneDesc = () => {
    switch (type) {
      case "url":
        return "지정된 웹 주소에서 이용약관 전문 데이터 크롤링 중...";
      case "document":
        return "업로드된 약관 파일 구조 분석 및 인코딩 변환 중...";
      case "name":
      default:
        return `${serviceName} 관련 공식 최신 이용약관 및 개정 이력 검색 중...`;
    }
  };

  const steps = [
    {
      id: "searching",
      title: "서비스 이용약관 수집 및 크롤링",
      description: getStepOneDesc(),
      icon: type === "url" ? Globe : type === "document" ? FileText : Search,
    },
    {
      id: "analyzing",
      title: "독소조항 감지 및 소비자 권리 분석",
      description: "AI 엔진을 통해 불공정 약관 요소, 환불 규정 및 자동 결제 독소조항 매핑 중...",
      icon: Sparkles,
    },
    {
      id: "completed",
      title: "맞춤형 약관 Q&A 가이드 빌더 구축 완료",
      description: "분석 완료! 1:1 맞춤형 약관 대화방 및 체크리스트가 준비되었습니다.",
      icon: ShieldCheck,
    },
  ];

  const getStepState = (stepId: string) => {
    if (stage === "completed") return "done";
    if (stepId === "searching") {
      return stage === "searching" ? "active" : "done";
    }
    if (stepId === "analyzing") {
      if (stage === "searching") return "pending";
      return stage === "analyzing" ? "active" : "done";
    }
    return "pending"; // completed step
  };

  return (
    <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-md z-[150] flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 15 }}
        transition={{ type: "spring", duration: 0.5 }}
        className="bg-surface-white border border-border-muted/80 rounded-3xl p-6 md:p-8 max-w-xl w-full shadow-2xl flex flex-col gap-6 relative overflow-hidden"
      >
        {/* Animated Background Subtle Aura */}
        <div className="absolute -right-24 -top-24 w-48 h-48 rounded-full bg-primary/10 blur-3xl" />
        <div className="absolute -left-24 -bottom-24 w-48 h-48 rounded-full bg-primary/5 blur-3xl" />

        {/* Header Block */}
        <div className="text-center relative z-10">
          <span className="px-3 py-1 bg-primary/10 text-primary rounded-full text-xs font-bold uppercase tracking-wider">
            Terms Analysis
          </span>
          <h3 className="text-xl md:text-2xl font-headline font-bold text-on-surface mt-3">
            '{serviceName}' 약관 분석 중
          </h3>
          <p className="text-sm text-on-surface-variant/70 mt-1.5 font-medium">
            FinePrint 법률 AI가 안전한 소비생활을 위해 분석을 시작합니다.
          </p>
        </div>

        {/* Dynamic Visual Centerpiece */}
        <div className="flex justify-center my-2 relative z-10">
          <div className="relative flex items-center justify-center w-24 h-24">
            {/* Spinning decorative ring */}
            {stage !== "completed" ? (
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ repeat: Infinity, duration: 2.5, ease: "linear" }}
                className="absolute inset-0 border-4 border-primary/20 border-t-primary rounded-full"
              />
            ) : (
              <motion.div
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: [1, 1.15, 1], opacity: 1 }}
                className="absolute inset-0 bg-primary/10 rounded-full"
                transition={{ duration: 0.6 }}
              />
            )}
            
            {/* Inner Icon */}
            <div className="w-16 h-16 rounded-full bg-primary/15 text-primary flex items-center justify-center relative z-20 shadow-sm">
              {stage === "completed" ? (
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: "spring", stiffness: 200, damping: 10 }}
                >
                  <ShieldCheck size={32} className="stroke-[2.5]" />
                </motion.div>
              ) : stage === "analyzing" ? (
                <Sparkles size={28} className="animate-pulse" />
              ) : (
                <Loader2 size={28} className="animate-spin" />
              )}
            </div>
          </div>
        </div>

        {/* Steps List */}
        <div className="flex flex-col gap-4 relative z-10 bg-slate-50/50 p-4 rounded-2xl border border-slate-100">
          {steps.map((step, idx) => {
            const state = getStepState(step.id);
            const StepIcon = step.icon;

            return (
              <div 
                key={step.id} 
                className={`flex gap-4.5 items-start transition-all duration-300 ${
                  state === "pending" ? "opacity-40" : "opacity-100"
                }`}
              >
                {/* Visual Bullet Line & State Icon */}
                <div className="flex flex-col items-center shrink-0">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center transition-all duration-300 border ${
                    state === "done" 
                      ? "bg-primary border-primary text-on-primary"
                      : state === "active"
                        ? "bg-primary-container border-primary text-primary shadow-xs ring-4 ring-primary/10"
                        : "bg-surface-white border-border-muted text-on-surface-variant/40"
                  }`}>
                    {state === "done" ? (
                      <Check size={16} className="stroke-[3]" />
                    ) : state === "active" ? (
                      <Loader2 size={15} className="animate-spin" />
                    ) : (
                      <span className="text-xs font-bold">{idx + 1}</span>
                    )}
                  </div>
                  {idx < steps.length - 1 && (
                    <div className={`w-0.5 h-10 transition-all duration-300 ${
                      state === "done" ? "bg-primary" : "bg-border-muted/50"
                    }`} />
                  )}
                </div>

                {/* Step Metadata */}
                <div className="min-w-0 flex-1 pt-0.5">
                  <div className="flex items-center gap-2">
                    <StepIcon size={14} className={state === "active" ? "text-primary animate-pulse" : state === "done" ? "text-primary" : "text-on-surface-variant/40"} />
                    <p className={`text-xs md:text-sm font-bold transition-all ${
                      state === "active" ? "text-primary" : "text-on-surface"
                    }`}>
                      {step.title}
                    </p>
                  </div>
                  <p className={`text-[11px] md:text-xs mt-1 transition-all ${
                    state === "active" ? "text-on-surface-variant/90 font-medium" : "text-on-surface-variant/50"
                  }`}>
                    {step.description}
                  </p>
                </div>
              </div>
            );
          })}
        </div>

        {/* Completion Action Alert Box */}
        {stage === "completed" && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-emerald-50 border border-emerald-200 rounded-xl p-3.5 flex items-center gap-3 relative z-10"
          >
            <div className="w-8 h-8 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0">
              <Check size={18} className="stroke-[2.5]" />
            </div>
            <div>
              <p className="text-xs font-bold text-emerald-900">약관 분석이 준비되었습니다!</p>
              <p className="text-[10px] text-emerald-800/80 font-medium mt-0.5">
                잠시 후 맞춤 질의응답 및 자동 환불 체크리스트 워크스페이스로 이동합니다.
              </p>
            </div>
          </motion.div>
        )}
      </motion.div>
    </div>
  );
}
