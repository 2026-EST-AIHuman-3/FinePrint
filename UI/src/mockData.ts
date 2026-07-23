import { HistoryItem } from "./types";

export const mockHistoryItems: HistoryItem[] = [
  {
    id: "yt-premium",
    serviceName: "YouTube Premium",
    type: "name",
    query: "YouTube Premium",
    date: "2026-07-19",
    queries: [
      {
        id: "yt-q1",
        question: "연간 구독을 중도 취소했는데 남은 기간에 대해 일할 계산 환불을 받을 수 있나요?",
        category: "refund",
        answer: "유튜브 프리미엄은 결제 주기 도중에 해지하더라도 남은 기간에 대한 일할 계산 환불을 원칙적으로 지원하지 않습니다. 해지 신청을 하더라도 현재 결제 주기가 끝날 때까지는 프리미엄 혜택이 계속 유지되며, 다음 주기부터 결제가 진행되지 않는 방식으로 처리됩니다. 단, 결제 후 전혀 이용하지 않은 상태로 7일 이내라면 구글 지원팀을 통해 전액 환불을 요청해 볼 수 있습니다.",
        evidence: "결제 주기 중간에 취소하더라도 사용하지 않은 잔여 일수에 대해 일할 계산하여 환불해 주지 않으며, 현재 청구 주기가 끝날 때까지 서비스 이용은 계속 유지됩니다.",
        originalText: "Refunds are not provided for partially unused billing periods. Upon cancellation, your access continues until the end of the current billing cycle.",
        todo: [
          { id: "yt-t1", text: "구글 플레이/유튜브 구매 항목 및 멤버십 메뉴에서 정기 결제 비활성화 해두기", checked: true },
          { id: "yt-t2", text: "이용 내역이 아예 없는 경우 결제 후 7일 이내에 Google 고객 지원팀에 직접 1:1 환불 메일 접수하기", checked: false }
        ],
        materials: ["구글 결제 프로필 ID 및 주문 번호 (G-로 시작)", "결제 완료 SMS 또는 카드 영수증 캡처본"],
        draft: "안녕하세요, YouTube Premium 결제 건에 대해 착오 결제로 인한 환불을 정중히 요청드립니다. 본 계정은 최근 정기 결제 이후 유튜브 프리미엄 서비스를 전혀 이용(시청 및 다운로드 등)하지 않았으며 결제일로부터 7일 이내입니다. 관련 규정에 의거하여 전액 청약철회 및 환불 처리를 부탁드립니다. 감사합니다.",
        timestamp: "23:01"
      },
      {
        id: "yt-q2",
        question: "구독 만료 전에 깜빡하고 해지를 못 하면 자동으로 1년치 금액이 전액 결제되나요?",
        category: "renewal",
        answer: "네, 유튜브 연간 구독권의 경우 만료 시점 최소 48시간 전까지 해지 예약을 해두지 않으면 동일한 연간 기간(12개월)으로 자동 갱신됩니다. 특히 최초 가입 시 받았던 프로모션이나 첫 해 할인 특가가 적용되어 있었다면, 갱신 시점에는 정상 가가 적용되어 훨씬 높은 금액이 청구될 수 있으므로 사전에 알림을 설정하고 취소를 미리 접수해 두는 행동이 필수적입니다.",
        evidence: "연간 구독 만료 48시간 전까지 해지하지 않으면 자동으로 동일한 12개월 조건으로 유료 자동 갱신되며, 요금은 할인 혜택이 미적용된 당시 정상가로 부과됩니다.",
        originalText: "Unless cancelled 48 hours prior to the anniversary date, the Subscription will automatically renew for a successive 12-month term at the then-prevailing non-discounted rate.",
        todo: [
          { id: "yt-t3", text: "구독 만료일 3일 전에 캘린더나 미리알림 앱에 '유튜브 결제 해지 확인' 푸시 등록하기", checked: false },
          { id: "yt-t4", text: "유튜브 멤버십 설정에서 '멤버십 비활성화(취소)'를 미리 완료하여 다음 주기 자동 결제 잠금 처리하기", checked: false }
        ],
        materials: ["현재 정기 결제 만료일 확인서 (유튜브 멤버십 화면 캡처)"],
        draft: "안녕하세요. 정기 구독 자동 결제 갱신 차단을 위해 본 메일을 발송합니다. 차기 12개월 연장 갱신을 원치 않으므로, 현재 이용 주기가 종료되는 즉시 추가 유료 승인 없이 해지 처리되도록 예약을 확인해 주시기 바랍니다.",
        timestamp: "23:05"
      }
    ],
    selectedQAId: "yt-q1"
  },
  {
    id: "nf-refund",
    serviceName: "Netflix",
    type: "name",
    query: "Netflix",
    date: "2026-07-18",
    queries: [
      {
        id: "nf-q1",
        question: "실수로 자동 결제가 되었는데, 프로필에서 영상을 1초만 재생했어도 환불이 아예 안 되나요?",
        category: "refund",
        answer: "넷플릭스는 한국 소비자 기본법 및 자체 약관에 의거하여 결제 후 7일 이내에 청약철회를 할 수 있도록 규정하고 있습니다. 하지만 매우 엄격한 '이용 실적 없음' 기준을 적용합니다. 계정 내 단 하나의 프로필에서라도 단 1초의 콘텐츠 스트리밍 기록이 있거나, 오프라인 다운로드 기록이 단 한 건이라도 잡힌다면 7일 이내라 하더라도 법적 환불이 불가능하며 당월 결제액은 소멸하게 됩니다.",
        evidence: "거래 발생일로부터 7일 이내에 전액 환불을 요청할 수 있으나, 계정에 연결된 어떠한 프로필에서도 영상 스트리밍 또는 다운로드 활동이 발생하지 않은 상태여야만 합니다.",
        originalText: "Members can request a full refund within 7 days of transaction, provided that no streaming or downloading activity has occurred on the account.",
        todo: [
          { id: "nf-t1", text: "착오 결제를 인지한 즉시 모든 연결 기기에서 넷플릭스 앱을 종료하고 절대 재생 버튼 누르지 않기", checked: true },
          { id: "nf-t2", text: "계정 프로필 시청 기록(Activity Log) 페이지에 접속하여 최근 시청 내역이 완전히 비어있는지 확인하기", checked: false },
          { id: "nf-t3", text: "재생 기록이 전혀 없다면 넷플릭스 공식 앱 내 '실시간 고객 센터 채팅'을 연결해 7일 이내 환불 긴급 요청하기", checked: false }
        ],
        materials: ["넷플릭스 계정 이메일 주소", "계정 시청 기록 페이지 화면 캡처", "카드사 승인 시간 정보"],
        draft: "안녕하세요, 넷플릭스 고객지원팀에 문의드립니다. 금일 자동 결제된 정기 구독 건에 대해 환불을 신청합니다. 결제 이후 어떠한 기기나 프로필에서도 영상 시청이나 오프라인 저장을 전혀 행하지 않았으며 완전히 비어있는 상태입니다. 7일 이내 청약철회 조건에 부합하므로 전액 환불 처리를 정중히 부탁드립니다.",
        timestamp: "18:32"
      }
    ],
    selectedQAId: "nf-q1"
  },
  {
    id: "sp-privacy",
    serviceName: "Spotify",
    type: "name",
    query: "Spotify",
    date: "2026-07-15",
    queries: [
      {
        id: "sp-q1",
        question: "제 음악 감상 취향이나 검색 기록 등의 정보가 타사 타겟팅 광고업체에 수집되어 전달되나요?",
        category: "privacy",
        answer: "네, 스포티파이의 정보보호 수집 동의 약관에 따르면 가명 처리된 사용자 정보(청취 기록, 장르 선호도, 디바이스 정보 및 추정 위치 정보 등)를 외부 광고 파트너사나 마케팅 대행사에 맞춤형 광고 집행 목적으로 공유할 권리를 보유하고 있습니다. 이를 차단하려면 회원을 탈퇴할 필요 없이 스포티파이 웹사이트 설정의 '개인정보 및 맞춤형 광고 설정' 메뉴에서 동의 체크를 직접 해제하셔야 데이터 추적 전송을 막을 수 있습니다.",
        evidence: "맞춤형 맞춤 마케팅 및 캠페인 제공을 목표로, 가명화 처리된 청취 습관, 고유 기기 식별값 및 IP 기반 기기 대략적 위치 데이터를 타사 광고주들과 공유할 수 있습니다.",
        originalText: "We may share pseudonymized listening history, device identifiers, and location-derived data with third-party advertisers to deliver customized ad campaigns.",
        todo: [
          { id: "sp-t1", text: "스포티파이 웹 홈페이지 로그인 후 [계정] -> [개인정보 설정]에서 '맞춤형 광고 동의' 끄기", checked: false },
          { id: "sp-t2", text: "페이스북이나 구글 등 소셜 간편 연동 가입자라면 소셜 보안 설정에서 스포티파이 앱 권한 제거 또는 이메일 기반 단독 계정으로 이전하기", checked: false }
        ],
        materials: ["없음 (설정 앱 내에서 토글 스위치 변경만으로 예방 가능)"],
        timestamp: "11:15"
      }
    ],
    selectedQAId: "sp-q1"
  }
];
