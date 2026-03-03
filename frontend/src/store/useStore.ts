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

/**
 * การตั้งค่าประสบการณ์ผู้ใช้ (เก็บใน localStorage, แชร์ผ่าน Store)
 */
export interface Preferences {
    notifSound: boolean; // เสียงแจ้งเตือนเมื่อได้รับข้อความใหม่
    notifDesktop: boolean; // Desktop Notification
    enterToSend: boolean; // Enter เพื่อส่ง
    fontSize: 'small' | 'medium' | 'large'; // ขนาดตัวอักษร
}

/** อ่านค่าเริ่มต้นจาก localStorage (ถ้าไม่มีใช้ default) */
function loadPrefs(): Preferences {
    const g = (k: string, def: string) => {
        // ตรวจสอบว่าอยู่ใน Browser และมี localStorage หรือไม่ (ป้องกัน Error ใน SSR)
        if (typeof window === 'undefined' || typeof localStorage === 'undefined' || !localStorage.getItem) {
            return def;
        }
        try {
            return localStorage.getItem(k) ?? def;
        } catch (e) {
            return def;
        }
    };
    return {
        notifSound: g('pref_notif_sound', 'true') !== 'false',
        notifDesktop: g('pref_notif_desktop', 'false') === 'true',
        enterToSend: g('pref_enter_send', 'true') !== 'false',
        fontSize: (g('pref_font_size', 'medium') as Preferences['fontSize']),
    };
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

    // Unread Counts
    unreadCounts: Record<string, number>;
    incrementUnread: (chatPartner: string) => void;
    clearUnread: (chatPartner: string) => void;

    // User Preferences
    preferences: Preferences;
    setPreference: <K extends keyof Preferences>(key: K, value: Preferences[K]) => void;

    // Security
    security: SecurityState;
    updateSecurity: (updates: Partial<SecurityState>) => void;
    resetSecurity: () => void;

    // ระบบ
    clearStore: () => void;
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

    // ─── Unread Counts ───
    unreadCounts: {},
    incrementUnread: (chatPartner) => set((state) => ({
        unreadCounts: {
            ...state.unreadCounts,
            [chatPartner]: (state.unreadCounts[chatPartner] ?? 0) + 1,
        },
    })),
    clearUnread: (chatPartner) => set((state) => ({
        unreadCounts: { ...state.unreadCounts, [chatPartner]: 0 },
    })),

    // ─── Preferences ───
    preferences: loadPrefs(),
    setPreference: (key, value) => {
        // บันทึกลง localStorage ทันทีขณะที่อัปเดต Store
        const lsKey: Record<keyof Preferences, string> = {
            notifSound: 'pref_notif_sound',
            notifDesktop: 'pref_notif_desktop',
            enterToSend: 'pref_enter_send',
            fontSize: 'pref_font_size',
        };

        // ตรวจสอบก่อนบันทึก (ป้องกัน Error ใน SSR หรือปิดคุกกี้)
        if (typeof window !== 'undefined' && typeof localStorage !== 'undefined' && localStorage.setItem) {
            try {
                localStorage.setItem(lsKey[key], String(value));
            } catch (e) {
                console.warn('Failed to save preference to localStorage:', e);
            }
        }

        set((state) => ({
            preferences: { ...state.preferences, [key]: value },
        }));
    },

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
        unreadCounts: {},
        security: {
            trustScore: 1.0,
            messageWindow: 0,
            isFrozen: false,
            currentMeta: initialMeta,
            ownerBaseline: initialBaseline,
        }
    })
}));
