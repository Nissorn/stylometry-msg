import { create } from 'zustand';

/**
 * โครงสร้างข้อมูลสำหรับข้อความแชท
 */
export interface Message {
    sender: string;
    content: string;
    timestamp: string;
}

/**
 * โครงสร้างข้อมูลสำหรับพฤติกรรมการพิมพ์ (Meta-stats)
 */
export interface MetaStats {
    length: number;    // ความยาวเฉลี่ย
    giggles: number;   // การใช้คำหัวเราะ (เช่น 555)
    elongation: number;// การลากเสียง (เช่น นนนน)
    punctuation: number;// การใช้เครื่องหมายวรรคตอน
    spacing: number;   // รูปแบบการเว้นวรรค
}

/**
 * สถานะความปลอดภัย (Security State)
 */
export interface SecurityState {
    trustScore: number;       // คะแนนความเชื่อมั่น (0.0 - 1.0)
    messageWindow: number;    // จำนวนข้อความใน window ปัจจุบัน (0-5)
    isFrozen: boolean;        // สถานะการล็อคหน้าจอ
    currentMeta: MetaStats;   // ค่า meta จาก session ปัจจุบัน
    ownerBaseline: MetaStats; // ค่า meta พื้นฐานของเจ้าของบัญชี
}

interface ChatStore {
    // Authentication
    currentUser: string | null;
    setCurrentUser: (username: string | null) => void;

    // Contacts & Active Chat
    contacts: string[];
    setContacts: (contacts: string[]) => void;
    activeContact: string | null;
    setActiveContact: (username: string | null) => void;

    // Messages
    messages: Record<string, Message[]>; // Key คือ username ของคู่สนทนา
    addMessage: (chatPartner: string, msg: Message) => void;
    setMessages: (chatPartner: string, msgs: Message[]) => void;

    // Security
    security: SecurityState;
    updateSecurity: (updates: Partial<SecurityState>) => void;
    resetSecurity: () => void;

    // ระบบ
    clearStore: () => void; // ฟังก์ชันสำหรับล้างข้อมูลทั้งหมดตอน Logout
}

const initialMeta: MetaStats = {
    length: 0,
    giggles: 0,
    elongation: 0,
    punctuation: 0,
    spacing: 0,
};

const initialBaseline: MetaStats = {
    length: 80,
    giggles: 60,
    elongation: 70,
    punctuation: 50,
    spacing: 40,
};

export const useStore = create<ChatStore>((set) => ({
    currentUser: null,
    setCurrentUser: (username) => set({ currentUser: username }),

    contacts: [],
    setContacts: (contacts) => set({ contacts }),
    activeContact: null,
    setActiveContact: (username) => set({ activeContact: username }),

    messages: {},
    addMessage: (chatPartner, msg) => set((state) => ({
        messages: {
            ...state.messages,
            [chatPartner]: [...(state.messages[chatPartner] || []), msg],
        },
    })),
    setMessages: (chatPartner, msgs) => set((state) => ({
        messages: {
            ...state.messages,
            [chatPartner]: msgs,
        },
    })),

    security: {
        trustScore: 1.0,
        messageWindow: 0,
        isFrozen: false,
        currentMeta: initialMeta,
        ownerBaseline: initialBaseline,
    },
    updateSecurity: (updates) => set((state) => ({
        security: { ...state.security, ...updates },
    })),
    resetSecurity: () => set({
        security: {
            trustScore: 1.0,
            messageWindow: 0,
            isFrozen: false,
            currentMeta: initialMeta,
            ownerBaseline: initialBaseline,
        }
    }),

    clearStore: () => set({
        currentUser: null,
        contacts: [],
        activeContact: null,
        messages: {},
        security: {
            trustScore: 1.0,
            messageWindow: 0,
            isFrozen: false,
            currentMeta: initialMeta,
            ownerBaseline: initialBaseline,
        }
    })
}));
