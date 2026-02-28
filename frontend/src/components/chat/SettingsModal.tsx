import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, User, Shield, Settings, CheckCircle, XCircle, Calendar, Users, Bell, BellOff, History, KeyRound, Loader2 } from 'lucide-react';
import { useStore } from '../../store/useStore';

interface Props {
    onClose: () => void;
    onOpenActivity: () => void;
}

type Tab = 'profile' | 'privacy' | 'general';

interface ProfileData {
    username: string;
    member_since: string | null;
    is_mfa_enabled: boolean;
    contact_count: number;
    calibration_progress: number;  // 0-5 messages sent to system_bot
}

/**
 * Settings & Profile Modal (3 Tabs)
 * - Profile  : ข้อมูลผู้ใช้ + สถานะ MFA
 * - Privacy  : ลิงก์ Audit Log + จัดการ MFA
 * - General  : การปรับแต่งเบื้องต้น (เสียงแจ้งเตือน ฯลฯ)
 */
const SettingsModal: React.FC<Props> = ({ onClose, onOpenActivity }) => {
    const [activeTab, setActiveTab] = useState<Tab>('profile');
    const [profile, setProfile]     = useState<ProfileData | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    // ─── General Tab preferences (ดึงจาก Zustand store — sync กับ localStorage อัตโนมัติ) ───
    const { preferences, setPreference } = useStore();
    const { notifSound, notifDesktop, enterToSend, fontSize } = preferences;

    // ─── โหลด Profile จาก API ───────────────────────────────────────
    useEffect(() => {
        (async () => {
            try {
                const res = await fetch('http://localhost:8000/api/user/profile', {
                    // @ts-ignore
                    credentials: 'include',
                });
                if (res.ok) {
                    const data = await res.json();
                    setProfile(data);
                }
            } catch (err) {
                console.error('Failed to load profile:', err);
            } finally {
                setIsLoading(false);
            }
        })();
    }, []);

    const formatDate = (iso: string | null) => {
        if (!iso) return 'ไม่ทราบ';
        return new Date(iso).toLocaleDateString('th-TH', {
            year: 'numeric', month: 'long', day: 'numeric',
        });
    };

    // ─── Tab config ─────────────────────────────────────────────────
    const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
        { key: 'profile', label: 'โปรไฟล์',  icon: <User size={15} />       },
        { key: 'privacy', label: 'ความเป็นส่วนตัว', icon: <Shield size={15} />  },
        { key: 'general', label: 'ทั่วไป',    icon: <Settings size={15} />   },
    ];

    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
            onClick={(e) => e.target === e.currentTarget && onClose()}
        >
            <motion.div
                initial={{ scale: 0.93, opacity: 0, y: 12 }}
                animate={{ scale: 1,    opacity: 1, y: 0  }}
                exit={{    scale: 0.93, opacity: 0, y: 12 }}
                transition={{ type: 'spring', stiffness: 320, damping: 28 }}
                className="bg-tg-sidebar w-full max-w-lg rounded-2xl shadow-2xl overflow-hidden border border-white/5"
            >
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 bg-tg-header border-b border-white/5">
                    <h2 className="text-white font-bold text-lg">การตั้งค่า</h2>
                    <button
                        onClick={onClose}
                        className="w-8 h-8 rounded-full flex items-center justify-center text-tg-text-secondary hover:text-white hover:bg-white/10 transition-all"
                    >
                        <X size={18} />
                    </button>
                </div>

                {/* Tabs */}
                <div className="flex border-b border-white/5 bg-tg-header/40">
                    {tabs.map((tab) => (
                        <button
                            key={tab.key}
                            onClick={() => setActiveTab(tab.key)}
                            className={`flex-1 flex items-center justify-center gap-1.5 py-3 text-sm font-medium transition-all ${
                                activeTab === tab.key
                                    ? 'text-tg-accent border-b-2 border-tg-accent'
                                    : 'text-tg-text-secondary hover:text-white'
                            }`}
                        >
                            {tab.icon}
                            {tab.label}
                        </button>
                    ))}
                </div>

                {/* Tab Content */}
                <div className="p-6 min-h-[320px]">
                    <AnimatePresence mode="wait">

                        {/* ─── Profile Tab ─── */}
                        {activeTab === 'profile' && (
                            <motion.div
                                key="profile"
                                initial={{ opacity: 0, x: -8 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{    opacity: 0, x:  8 }}
                                transition={{ duration: 0.18 }}
                                className="space-y-4"
                            >
                                {isLoading ? (
                                    <div className="flex justify-center py-12">
                                        <Loader2 size={28} className="animate-spin text-tg-accent" />
                                    </div>
                                ) : (
                                    <>
                                        {/* Avatar + ชื่อ */}
                                        <div className="flex items-center gap-4">
                                            <div className="w-16 h-16 bg-tg-accent rounded-full flex items-center justify-center text-2xl font-bold text-white shadow-lg shrink-0">
                                                {profile?.username?.[0]?.toUpperCase() ?? '?'}
                                            </div>
                                            <div>
                                                <div className="text-white font-bold text-xl leading-tight">
                                                    {profile?.username ?? '—'}
                                                </div>
                                                <div className="text-tg-text-secondary text-sm mt-0.5">
                                                    @{profile?.username ?? '—'}
                                                </div>
                                            </div>
                                        </div>

                                        {/* Stats Cards */}
                                        <div className="grid grid-cols-2 gap-3 mt-2">
                                            <div className="bg-tg-header rounded-xl p-3 flex items-center gap-3">
                                                <Calendar size={18} className="text-tg-accent shrink-0" />
                                                <div>
                                                    <div className="text-[11px] text-tg-text-secondary uppercase tracking-wide">สมาชิกตั้งแต่</div>
                                                    <div className="text-white text-sm font-medium">
                                                        {formatDate(profile?.member_since ?? null)}
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="bg-tg-header rounded-xl p-3 flex items-center gap-3">
                                                <Users size={18} className="text-tg-accent shrink-0" />
                                                <div>
                                                    <div className="text-[11px] text-tg-text-secondary uppercase tracking-wide">ผู้ติดต่อ</div>
                                                    <div className="text-white text-sm font-medium">
                                                        {profile?.contact_count ?? 0} คน
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        {/* MFA Status */}
                                        <div className="bg-tg-header rounded-xl p-4 flex items-center justify-between">
                                            <div className="flex items-center gap-3">
                                                <Shield size={20} className={profile?.is_mfa_enabled ? 'text-green-400' : 'text-yellow-400'} />
                                                <div>
                                                    <div className="text-white font-medium text-sm">การยืนยันตัวตน 2 ชั้น</div>
                                                    <div className="text-tg-text-secondary text-xs">TOTP / Authenticator App</div>
                                                </div>
                                            </div>
                                            {profile?.is_mfa_enabled ? (
                                                <span className="flex items-center gap-1.5 text-green-400 text-sm font-semibold">
                                                    <CheckCircle size={16} /> เปิดใช้งาน
                                                </span>
                                            ) : (
                                                <span className="flex items-center gap-1.5 text-yellow-400 text-sm font-semibold">
                                                    <XCircle size={16} /> ยังไม่ได้ตั้งค่า
                                                </span>
                                            )}
                                        </div>

                                        {/* ─── Security Health & Stylometry ─── */}
                                        {(() => {
                                            const prog = profile?.calibration_progress ?? 0;
                                            const pct  = Math.round((prog / 5) * 100);
                                            return prog >= 5 ? (
                                                /* ✅ Baseline เสร็จแล้ว */
                                                <div className="bg-green-500/10 border border-green-500/25 rounded-xl p-4 flex items-center gap-3">
                                                    <div className="w-9 h-9 bg-green-500/20 rounded-lg flex items-center justify-center shrink-0">
                                                        <Shield size={18} className="text-green-400" />
                                                    </div>
                                                    <div>
                                                        <div className="text-green-400 font-semibold text-sm">Identity Baseline Created ✅</div>
                                                        <div className="text-green-300/70 text-xs mt-0.5">ระบบจดจำเอกลักษณ์การพิมพ์ของคุณเรียบร้อยแล้ว</div>
                                                    </div>
                                                </div>
                                            ) : (
                                                /* ⏳ ยัง Calibrate อยู่ */
                                                <div className="bg-tg-header rounded-xl p-4 space-y-2">
                                                    <div className="flex items-center justify-between">
                                                        <div className="flex items-center gap-2">
                                                            <Shield size={16} className="text-tg-accent" />
                                                            <span className="text-white text-sm font-medium">Security Health &amp; Stylometry</span>
                                                        </div>
                                                        <span className="text-tg-accent text-xs font-semibold">Calibration: {prog}/5</span>
                                                    </div>
                                                    {/* Progress bar */}
                                                    <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
                                                        <div
                                                            className="h-full bg-tg-accent rounded-full transition-all duration-500"
                                                            style={{ width: `${pct}%` }}
                                                        />
                                                    </div>
                                                    <div className="text-tg-text-secondary text-xs">
                                                        กำลังเรียนรู้สไตล์การพิมพ์ผ่านการคุยกับ Stylometry Guardian...
                                                    </div>
                                                </div>
                                            );
                                        })()}
                                    </>
                                )}
                            </motion.div>
                        )}

                        {/* ─── Privacy Tab ─── */}
                        {activeTab === 'privacy' && (
                            <motion.div
                                key="privacy"
                                initial={{ opacity: 0, x: -8 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{    opacity: 0, x:  8 }}
                                transition={{ duration: 0.18 }}
                                className="space-y-3"
                            >
                                <p className="text-tg-text-secondary text-sm mb-4">
                                    ตามหลัก Digital ID คุณมีสิทธิ์รู้และควบคุมข้อมูลของตัวเองทั้งหมด
                                </p>

                                {/* Activity Log */}
                                <button
                                    onClick={() => { onClose(); onOpenActivity(); }}
                                    className="w-full bg-tg-header hover:bg-tg-header/80 rounded-xl p-4 flex items-center gap-3 text-left transition-all group"
                                >
                                    <div className="w-9 h-9 bg-tg-accent/20 rounded-lg flex items-center justify-center shrink-0 group-hover:bg-tg-accent/30 transition-colors">
                                        <History size={18} className="text-tg-accent" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-white font-medium text-sm">ประวัติการเข้าใช้งาน</div>
                                        <div className="text-tg-text-secondary text-xs truncate">ดู Audit Log ทั้งหมด — Login, MFA, Alerts</div>
                                    </div>
                                </button>

                                {/* MFA Management */}
                                <div className="bg-tg-header rounded-xl p-4 flex items-center gap-3">
                                    <div className="w-9 h-9 bg-tg-accent/20 rounded-lg flex items-center justify-center shrink-0">
                                        <KeyRound size={18} className="text-tg-accent" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-white font-medium text-sm">การตั้งค่า MFA</div>
                                        <div className="text-tg-text-secondary text-xs">
                                            {isLoading ? '...' : (
                                                profile?.is_mfa_enabled
                                                    ? 'TOTP เปิดใช้งานอยู่แล้ว ✅'
                                                    : 'ยังไม่ได้ตั้งค่า — สมัครใหม่เพื่อตั้งค่า'
                                            )}
                                        </div>
                                    </div>
                                    {!isLoading && profile?.is_mfa_enabled && (
                                        <span className="text-green-400 shrink-0">
                                            <CheckCircle size={18} />
                                        </span>
                                    )}
                                </div>

                                {/* Digital ID Note */}
                                <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl p-3 mt-2">
                                    <p className="text-blue-300 text-xs leading-relaxed">
                                        🔐 <span className="font-semibold">Digital ID</span> ของระบบนี้ใช้ Stylometry + MFA
                                        เพื่อยืนยันว่าคนที่กำลังใช้งานคือเจ้าของบัญชีจริง
                                        ข้อมูลทุกอย่างถูกเข้ารหัส (Fernet E2E) และเก็บเป็น Audit Log
                                    </p>
                                </div>
                            </motion.div>
                        )}

                        {/* ─── General Tab ─── */}
                        {activeTab === 'general' && (
                            <motion.div
                                key="general"
                                initial={{ opacity: 0, x: -8 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{    opacity: 0, x:  8 }}
                                transition={{ duration: 0.18 }}
                                className="space-y-4"
                            >
                                {/* Toggle rows */}
                                {[
                                    {
                                        label: 'เสียงแจ้งเตือนข้อความ',
                                        sublabel: 'เล่นเสียงเมื่อได้รับข้อความใหม่',
                                        icon: notifSound ? <Bell size={18} className="text-tg-accent" /> : <BellOff size={18} className="text-tg-text-secondary" />,
                                        value: notifSound,
                                        onChange: (v: boolean) => setPreference('notifSound', v),
                                    },
                                    {
                                        label: 'การแจ้งเตือน Desktop',
                                        sublabel: 'แสดง Notification บน OS เมื่อมีข้อความใหม่',
                                        icon: <Bell size={18} className={notifDesktop ? 'text-tg-accent' : 'text-tg-text-secondary'} />,
                                        value: notifDesktop,
                                        onChange: (v: boolean) => setPreference('notifDesktop', v),
                                    },
                                    {
                                        label: 'Enter เพื่อส่ง',
                                        sublabel: 'กด Enter เพื่อส่งข้อความ (Shift+Enter ขึ้นบรรทัดใหม่)',
                                        icon: <Settings size={18} className={enterToSend ? 'text-tg-accent' : 'text-tg-text-secondary'} />,
                                        value: enterToSend,
                                        onChange: (v: boolean) => setPreference('enterToSend', v),
                                    },
                                ].map((row) => (
                                    <div key={row.label} className="flex items-center justify-between bg-tg-header rounded-xl px-4 py-3">
                                        <div className="flex items-center gap-3">
                                            {row.icon}
                                            <div>
                                                <div className="text-white text-sm font-medium">{row.label}</div>
                                                <div className="text-tg-text-secondary text-xs">{row.sublabel}</div>
                                            </div>
                                        </div>
                                        {/* Toggle Switch */}
                                        <button
                                            type="button"
                                            role="switch"
                                            aria-checked={row.value}
                                            onClick={() => row.onChange(!row.value)}
                                            className={`relative w-10 h-5 rounded-full transition-colors shrink-0 ${
                                                row.value ? 'bg-tg-accent' : 'bg-white/20'
                                            }`}
                                        >
                                            <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${
                                                row.value ? 'left-5' : 'left-0.5'
                                            }`} />
                                        </button>
                                    </div>
                                ))}

                                {/* Font size selector */}
                                <div className="bg-tg-header rounded-xl px-4 py-3">
                                    <div className="flex items-center justify-between mb-2">
                                        <div className="text-white text-sm font-medium">ขนาดตัวอักษร</div>
                                        <span className="text-tg-accent text-xs capitalize">{fontSize === 'small' ? 'เล็ก' : fontSize === 'large' ? 'ใหญ่' : 'กลาง'}</span>
                                    </div>
                                    <div className="flex gap-2">
                                        {(['small', 'medium', 'large'] as const).map((s) => (
                                            <button
                                                key={s}
                                                onClick={() => setPreference('fontSize', s)}
                                                className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-all ${
                                                    fontSize === s
                                                        ? 'bg-tg-accent text-white'
                                                        : 'bg-white/10 text-tg-text-secondary hover:text-white'
                                                }`}
                                            >
                                                {s === 'small' ? 'เล็ก' : s === 'medium' ? 'กลาง' : 'ใหญ่'}
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                <p className="text-tg-text-secondary text-xs text-center pt-1">
                                    การตั้งค่าเหล่านี้บันทึกเฉพาะเครื่องนี้
                                </p>
                            </motion.div>
                        )}

                    </AnimatePresence>
                </div>
            </motion.div>
        </motion.div>
    );
};

export default SettingsModal;
