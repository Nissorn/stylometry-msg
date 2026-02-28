import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    X, ShieldCheck, ShieldAlert, LogIn, LogOut,
    MessageSquare, UserPlus, AlertTriangle, RefreshCw,
    Monitor, Smartphone, Globe
} from 'lucide-react';

// ---- Types ----
interface AuditLog {
    id: string;
    user_id: string | null;
    action: string;
    ip_address: string;
    user_agent: string;
    extra_data: Record<string, unknown>;
    timestamp: string;
}

interface ActivityLogModalProps {
    onClose: () => void;
}

// ---- Helpers ----

/**
 * แปลง User-Agent string ให้อ่านง่าย
 * เช่น "Chrome บน Windows", "Safari บน iPhone"
 */
function parseUserAgent(ua: string): { browser: string; os: string; icon: React.ReactNode } {
    const s = ua.toLowerCase();

    // ตรวจจับ Browser
    let browser = 'Unknown Browser';
    if (s.includes('edg/') || s.includes('edge/')) browser = 'Edge';
    else if (s.includes('opr/') || s.includes('opera')) browser = 'Opera';
    else if (s.includes('chrome') || s.includes('crios')) browser = 'Chrome';
    else if (s.includes('firefox') || s.includes('fxios')) browser = 'Firefox';
    else if (s.includes('safari')) browser = 'Safari';
    else if (s.includes('curl')) browser = 'cURL';
    else if (s.includes('python')) browser = 'Python';

    // ตรวจจับ OS
    let os = 'Unknown OS';
    let icon: React.ReactNode = <Monitor size={12} />;
    if (s.includes('android')) { os = 'Android'; icon = <Smartphone size={12} />; }
    else if (s.includes('iphone') || s.includes('ipad')) { os = 'iOS'; icon = <Smartphone size={12} />; }
    else if (s.includes('windows')) { os = 'Windows'; icon = <Monitor size={12} />; }
    else if (s.includes('mac os') || s.includes('macintosh')) { os = 'macOS'; icon = <Monitor size={12} />; }
    else if (s.includes('linux')) { os = 'Linux'; icon = <Monitor size={12} />; }

    return { browser, os, icon };
}

/**
 * แปลง action code เป็นข้อความและสีที่อ่านง่าย
 */
function getActionMeta(action: string): {
    label: string;
    colorClass: string;
    bgClass: string;
    icon: React.ReactNode;
} {
    switch (action) {
        case 'LOGIN_SUCCESS':
            return { label: 'เข้าสู่ระบบสำเร็จ', colorClass: 'text-green-400', bgClass: 'bg-green-500/10 border-green-500/20', icon: <LogIn size={13} /> };
        case 'LOGIN_FAILED':
            return { label: 'เข้าสู่ระบบล้มเหลว', colorClass: 'text-red-400', bgClass: 'bg-red-500/10 border-red-500/20', icon: <ShieldAlert size={13} /> };
        case 'LOGOUT':
            return { label: 'ออกจากระบบ', colorClass: 'text-amber-400', bgClass: 'bg-amber-500/10 border-amber-500/20', icon: <LogOut size={13} /> };
        case 'REGISTER':
            return { label: 'ลงทะเบียนบัญชี', colorClass: 'text-tg-accent', bgClass: 'bg-tg-accent/10 border-tg-accent/20', icon: <ShieldCheck size={13} /> };
        case 'SEND_MESSAGE':
            return { label: 'ส่งข้อความ', colorClass: 'text-tg-text-secondary', bgClass: 'bg-white/5 border-white/10', icon: <MessageSquare size={13} /> };
        case 'ADD_CONTACT':
            return { label: 'เพิ่มรายชื่อ', colorClass: 'text-purple-400', bgClass: 'bg-purple-500/10 border-purple-500/20', icon: <UserPlus size={13} /> };
        case 'STYLOMETRY_ALERT':
            return { label: '⚠ Stylometry Alert', colorClass: 'text-red-400', bgClass: 'bg-red-500/15 border-red-500/30', icon: <AlertTriangle size={13} /> };
        default:
            return { label: action, colorClass: 'text-tg-text-secondary', bgClass: 'bg-white/5 border-white/10', icon: <Globe size={13} /> };
    }
}

/**
 * Format timestamp เป็น "28 ก.พ. 2569 · 14:30"
 */
function formatTimestamp(iso: string): { date: string; time: string } {
    const d = new Date(iso);
    const date = d.toLocaleDateString('th-TH', { day: 'numeric', month: 'short', year: 'numeric' });
    const time = d.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });
    return { date, time };
}

// ---- Component ----

const ActivityLogModal: React.FC<ActivityLogModalProps> = ({ onClose }) => {
    const [logs, setLogs] = useState<AuditLog[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState('');
    const [filter, setFilter] = useState<string>('ALL');

    const fetchLogs = useCallback(async () => {
        setIsLoading(true);
        setError('');
        try {
            const res = await fetch('http://localhost:8000/api/me/logs', {
                // @ts-ignore
                credentials: 'include',
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            // เรียงล่าสุดก่อน
            const sorted = [...(data.logs as AuditLog[])].sort(
                (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
            );
            setLogs(sorted);
        } catch (e) {
            setError('ไม่สามารถโหลดข้อมูลได้ กรุณาลองอีกครั้ง');
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchLogs();
    }, [fetchLogs]);

    // Close on Escape key
    useEffect(() => {
        const handleKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', handleKey);
        return () => window.removeEventListener('keydown', handleKey);
    }, [onClose]);

    const FILTER_OPTIONS = [
        { key: 'ALL', label: 'ทั้งหมด' },
        { key: 'LOGIN_SUCCESS', label: 'เข้าระบบ' },
        { key: 'LOGIN_FAILED', label: 'ล้มเหลว' },
        { key: 'STYLOMETRY_ALERT', label: 'แจ้งเตือน' },
        { key: 'SEND_MESSAGE', label: 'ข้อความ' },
    ];

    const filteredLogs = filter === 'ALL' ? logs : logs.filter((l) => l.action === filter);

    return (
        <div
            className="fixed inset-0 z-200 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
            onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
        >
            <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 16 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 16 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
                className="w-full max-w-2xl bg-tg-sidebar rounded-2xl border border-white/10 shadow-2xl flex flex-col overflow-hidden"
                style={{ maxHeight: '85vh' }}
            >
                {/* ─── Header ─── */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-[#1c2733] shrink-0">
                    <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-xl bg-tg-accent/15 flex items-center justify-center">
                            <ShieldCheck size={18} className="text-tg-accent" />
                        </div>
                        <div>
                            <h2 className="text-white font-bold text-base leading-tight">ประวัติการเข้าใช้งาน</h2>
                            <p className="text-tg-text-secondary text-[11px]">Security Activity Log</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={fetchLogs}
                            disabled={isLoading}
                            className="w-8 h-8 rounded-lg bg-white/5 hover:bg-white/10 flex items-center justify-center transition-all text-tg-text-secondary hover:text-white disabled:opacity-40"
                            title="รีเฟรช"
                        >
                            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
                        </button>
                        <button
                            onClick={onClose}
                            className="w-8 h-8 rounded-lg bg-white/5 hover:bg-red-500/20 flex items-center justify-center transition-all text-tg-text-secondary hover:text-red-400"
                        >
                            <X size={16} />
                        </button>
                    </div>
                </div>

                {/* ─── Filter Tabs ─── */}
                <div className="flex gap-1.5 px-4 py-3 border-b border-white/5 bg-[#1c2733] shrink-0 overflow-x-auto">
                    {FILTER_OPTIONS.map((opt) => (
                        <button
                            key={opt.key}
                            onClick={() => setFilter(opt.key)}
                            className={`px-3 py-1 rounded-full text-xs font-medium transition-all whitespace-nowrap ${
                                filter === opt.key
                                    ? 'bg-tg-accent text-white shadow-sm'
                                    : 'bg-white/5 text-tg-text-secondary hover:bg-white/10 hover:text-white'
                            }`}
                        >
                            {opt.label}
                            {opt.key !== 'ALL' && (
                                <span className="ml-1.5 opacity-60">
                                    {logs.filter((l) => l.action === opt.key).length}
                                </span>
                            )}
                        </button>
                    ))}
                </div>

                {/* ─── Content ─── */}
                <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
                    {isLoading ? (
                        <div className="flex flex-col items-center justify-center py-16 gap-3">
                            <div className="w-8 h-8 border-2 border-tg-accent border-t-transparent rounded-full animate-spin" />
                            <p className="text-tg-text-secondary text-sm">กำลังโหลด...</p>
                        </div>
                    ) : error ? (
                        <div className="flex flex-col items-center justify-center py-16 gap-3">
                            <AlertTriangle size={32} className="text-red-400 opacity-60" />
                            <p className="text-red-400 text-sm">{error}</p>
                            <button
                                onClick={fetchLogs}
                                className="mt-1 px-4 py-1.5 rounded-lg bg-red-500/10 text-red-400 text-xs hover:bg-red-500/20 transition-all border border-red-500/20"
                            >
                                ลองอีกครั้ง
                            </button>
                        </div>
                    ) : filteredLogs.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-16 gap-2">
                            <ShieldCheck size={32} className="text-tg-text-secondary opacity-40" />
                            <p className="text-tg-text-secondary text-sm">ไม่พบรายการ</p>
                        </div>
                    ) : (
                        filteredLogs.map((log) => {
                            const meta = getActionMeta(log.action);
                            const { browser, os, icon } = parseUserAgent(log.user_agent);
                            const { date, time } = formatTimestamp(log.timestamp);
                            return (
                                <motion.div
                                    key={log.id}
                                    initial={{ opacity: 0, x: -8 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    className={`flex items-start gap-3 p-3.5 rounded-xl border ${meta.bgClass} transition-all hover:brightness-110`}
                                >
                                    {/* Event Icon */}
                                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5 ${meta.colorClass} bg-current/10`}
                                        style={{ background: 'transparent' }}>
                                        <span className={meta.colorClass}>{meta.icon}</span>
                                    </div>

                                    {/* Main Info */}
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center justify-between gap-2">
                                            <span className={`text-sm font-semibold ${meta.colorClass}`}>
                                                {meta.label}
                                            </span>
                                            <div className="text-right shrink-0">
                                                <div className="text-[11px] text-white/80">{time}</div>
                                                <div className="text-[10px] text-tg-text-secondary">{date}</div>
                                            </div>
                                        </div>

                                        {/* Device & IP Row */}
                                        <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                                            <span className="flex items-center gap-1 text-[11px] text-tg-text-secondary">
                                                {icon}
                                                <span>{browser} บน {os}</span>
                                            </span>
                                            <span className="flex items-center gap-1 text-[11px] text-tg-text-secondary">
                                                <Globe size={11} />
                                                <span className="font-mono">{log.ip_address}</span>
                                            </span>
                                        </div>

                                        {/* Extra Data (ถ้ามี) */}
                                        {Object.keys(log.extra_data).length > 0 && (
                                            <div className="mt-1.5 flex flex-wrap gap-1.5">
                                                {Object.entries(log.extra_data).map(([k, v]) => (
                                                    <span
                                                        key={k}
                                                        className="px-2 py-0.5 rounded-md bg-white/5 text-[10px] text-tg-text-secondary border border-white/5"
                                                    >
                                                        <span className="opacity-60">{k}: </span>
                                                        <span className="text-white/70">{String(v)}</span>
                                                    </span>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                </motion.div>
                            );
                        })
                    )}
                </div>

                {/* ─── Footer ─── */}
                {!isLoading && !error && (
                    <div className="px-6 py-3 border-t border-white/5 bg-[#1c2733] shrink-0 flex items-center justify-between">
                        <span className="text-[11px] text-tg-text-secondary">
                            {filteredLogs.length} รายการ{filter !== 'ALL' && ` (กรอง)`}
                        </span>
                        <span className="text-[11px] text-tg-text-secondary opacity-50 uppercase tracking-widest">
                            Thai Stylometry Security Log
                        </span>
                    </div>
                )}
            </motion.div>
        </div>
    );
};

export default ActivityLogModal;
