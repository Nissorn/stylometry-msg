import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useStore } from '../../store/useStore';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Lock, User, LogIn, UserPlus, ShieldCheck, Smartphone,
    Copy, CheckCheck, ArrowLeft, KeyRound, AlertTriangle, Eye, EyeOff
} from 'lucide-react';

// ─────────────────────────────────────────
//  Types
// ─────────────────────────────────────────

type AuthStep =
    | 'credentials'       // ฟอร์ม username / password
    | 'mfa_setup'         // แสดง QR Code + กรอก OTP ครั้งแรก
    | 'mfa_challenge';    // กรอก OTP สำหรับ Login ปกติ

// ─────────────────────────────────────────
//  Sub-component: 6-digit OTP Input
// ─────────────────────────────────────────

interface OtpInputProps {
    value: string;
    onChange: (v: string) => void;
    disabled?: boolean;
    autoFocus?: boolean;
}

const OtpInput: React.FC<OtpInputProps> = ({ value, onChange, disabled, autoFocus }) => {
    const inputs = useRef<(HTMLInputElement | null)[]>([]);

    const digits = value.padEnd(6, '').split('').slice(0, 6);

    const handleKey = (i: number, e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Backspace') {
            if (digits[i]) {
                const next = digits.map((d, idx) => (idx === i ? '' : d)).join('').replace(/ /g, '');
                onChange(next);
            } else if (i > 0) {
                inputs.current[i - 1]?.focus();
            }
        }
    };

    const handleChange = (i: number, e: React.ChangeEvent<HTMLInputElement>) => {
        const raw = e.target.value.replace(/\D/g, '');
        if (!raw) return;
        const chars = raw.split('');
        const newDigits = [...digits];
        let nextFocus = i;
        chars.forEach((ch, offset) => {
            if (i + offset < 6) {
                newDigits[i + offset] = ch;
                nextFocus = i + offset;
            }
        });
        onChange(newDigits.join('').substring(0, 6));
        const focusIdx = Math.min(nextFocus + 1, 5);
        setTimeout(() => inputs.current[focusIdx]?.focus(), 0);
    };

    const handlePaste = (e: React.ClipboardEvent) => {
        e.preventDefault();
        const text = e.clipboardData.getData('text').replace(/\D/g, '').substring(0, 6);
        onChange(text);
        const focusIdx = Math.min(text.length, 5);
        setTimeout(() => inputs.current[focusIdx]?.focus(), 0);
    };

    return (
        <div className="flex gap-2.5 justify-center">
            {[0, 1, 2, 3, 4, 5].map((i) => (
                <input
                    key={i}
                    ref={(el) => { inputs.current[i] = el; }}
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    maxLength={1}
                    value={digits[i] || ''}
                    autoFocus={autoFocus && i === 0}
                    disabled={disabled}
                    onKeyDown={(e) => handleKey(i, e)}
                    onChange={(e) => handleChange(i, e)}
                    onPaste={handlePaste}
                    onFocus={(e) => e.target.select()}
                    className={`w-11 h-14 text-center text-xl font-bold rounded-xl border-2 outline-none transition-all bg-tg-bg text-white caret-transparent
                        ${digits[i]
                            ? 'border-tg-accent shadow-[0_0_12px_rgba(82,136,193,0.35)]'
                            : 'border-white/10 hover:border-white/20 focus:border-tg-accent/60'
                        }
                        ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                />
            ))}
        </div>
    );
};

// ─────────────────────────────────────────
//  Sub-component: MFA Setup Screen
// ─────────────────────────────────────────

interface MfaSetupScreenProps {
    setupToken: string;
    isAdaptive?: boolean;
    username: string;
    onSuccess: () => void;
    onBack: () => void;
}

const MfaSetupScreen: React.FC<MfaSetupScreenProps> = ({
    setupToken, isAdaptive, username, onSuccess, onBack
}) => {
    const [qrBase64, setQrBase64] = useState('');
    const [secret, setSecret] = useState('');
    const [otp, setOtp] = useState('');
    const [phase, setPhase] = useState<'loading' | 'scan' | 'verify'>('loading');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const [copied, setCopied] = useState(false);

    useEffect(() => {
        const fetchQr = async () => {
            try {
                const res = await fetch('http://localhost:8000/api/auth/mfa/setup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ setup_token: setupToken }),
                    // @ts-ignore
                    credentials: 'include',
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Setup failed');
                setQrBase64(data.qr_code_base64);
                setSecret(data.secret);
                setPhase('scan');
            } catch (e: any) {
                setError(e.message);
                setPhase('scan');
            }
        };
        fetchQr();
    }, [setupToken]);

    const handleCopySecret = async () => {
        await navigator.clipboard.writeText(secret);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const handleVerify = async (e: React.FormEvent) => {
        e.preventDefault();
        if (otp.length !== 6) return;
        setLoading(true);
        setError('');
        try {
            const res = await fetch('http://localhost:8000/api/auth/mfa/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: setupToken, code: otp }),
                // @ts-ignore
                credentials: 'include',
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Verification failed');
            onSuccess();
        } catch (e: any) {
            setError(e.message);
            setOtp('');
        } finally {
            setLoading(false);
        }
    };

    return (
        <motion.div
            key="mfa_setup"
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -40 }}
            className="w-full"
        >
            <div className="flex items-center gap-3 mb-6">
                <button
                    onClick={onBack}
                    className="w-8 h-8 rounded-lg bg-white/5 hover:bg-white/10 flex items-center justify-center text-tg-text-secondary hover:text-white transition-all shrink-0"
                >
                    <ArrowLeft size={16} />
                </button>
                <div>
                    <h3 className="text-white font-bold text-lg leading-tight">ตั้งค่าการยืนยันตัวตน</h3>
                    <p className="text-tg-text-secondary text-xs mt-0.5">
                        {isAdaptive
                            ? 'ตรวจพบอุปกรณ์ใหม่ — โปรดตั้งค่า 2FA ก่อนดำเนินการ'
                            : 'Two-Factor Authentication Setup'}
                    </p>
                </div>
            </div>

            {isAdaptive && (
                <div className="flex items-start gap-2.5 bg-amber-500/10 border border-amber-500/25 rounded-xl px-4 py-3 mb-5">
                    <AlertTriangle size={16} className="text-amber-400 shrink-0 mt-0.5" />
                    <p className="text-amber-300 text-xs leading-relaxed">
                        ระบบตรวจพบว่าคุณกำลังเข้าสู่ระบบจาก <strong>อุปกรณ์/เครือข่ายใหม่</strong>
                        <br />กรุณาสแกน QR Code เพื่อเพิ่มชั้นความปลอดภัย
                    </p>
                </div>
            )}

            {/* Step tabs */}
            <div className="flex gap-1 bg-tg-bg rounded-xl p-1 mb-6">
                {['สแกน QR Code', 'ยืนยันรหัส'].map((label, idx) => (
                    <button
                        key={idx}
                        onClick={() => idx === 1 && setPhase('verify')}
                        className={`flex-1 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                            (idx === 0 ? phase === 'scan' || phase === 'loading' : phase === 'verify')
                                ? 'bg-tg-accent text-white'
                                : 'text-tg-text-secondary hover:text-white'
                        }`}
                    >
                        {idx + 1}. {label}
                    </button>
                ))}
            </div>

            <AnimatePresence mode="wait">
                {phase === 'loading' && (
                    <motion.div
                        key="loading"
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        className="flex justify-center py-12"
                    >
                        <div className="w-8 h-8 border-2 border-tg-accent border-t-transparent rounded-full animate-spin" />
                    </motion.div>
                )}

                {phase === 'scan' && (
                    <motion.div
                        key="scan"
                        initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
                        className="space-y-5"
                    >
                        <div className="flex flex-col items-center gap-1 text-tg-text-secondary text-sm text-center">
                            <Smartphone size={18} className="text-tg-accent mb-1" />
                            <p>เปิดแอป <strong className="text-white">Google Authenticator</strong> หรือ <strong className="text-white">Authy</strong></p>
                            <p className="text-xs">แล้วสแกน QR Code ด้านล่าง</p>
                        </div>

                        {qrBase64 ? (
                            <div className="flex justify-center">
                                <div className="p-3 bg-white rounded-2xl shadow-lg shadow-tg-accent/10 border border-tg-accent/20">
                                    <img
                                        src={`data:image/png;base64,${qrBase64}`}
                                        alt="MFA QR Code"
                                        className="w-44 h-44 rounded-lg"
                                    />
                                </div>
                            </div>
                        ) : (
                            <div className="flex justify-center">
                                <div className="w-44 h-44 rounded-2xl bg-tg-header flex items-center justify-center">
                                    <span className="text-red-400 text-xs text-center px-4">{error || 'ไม่สามารถโหลด QR ได้'}</span>
                                </div>
                            </div>
                        )}

                        {secret && (
                            <div className="bg-tg-bg rounded-xl p-3 border border-white/5">
                                <div className="text-[10px] text-tg-text-secondary uppercase tracking-wider mb-2">
                                    Setup Key (สำหรับกรอกแทน QR)
                                </div>
                                <div className="flex items-center gap-2">
                                    <code className="flex-1 font-mono text-xs text-tg-accent break-all">{secret}</code>
                                    <button
                                        onClick={handleCopySecret}
                                        className="shrink-0 w-7 h-7 rounded-lg bg-tg-header hover:bg-tg-accent/20 flex items-center justify-center transition-all"
                                    >
                                        {copied
                                            ? <CheckCheck size={13} className="text-green-400" />
                                            : <Copy size={13} className="text-tg-text-secondary" />}
                                    </button>
                                </div>
                            </div>
                        )}

                        <button onClick={() => setPhase('verify')} className="tg-button">
                            สแกนเสร็จแล้ว → กรอกรหัสยืนยัน
                        </button>
                    </motion.div>
                )}

                {phase === 'verify' && (
                    <motion.div
                        key="verify"
                        initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
                    >
                        <form onSubmit={handleVerify} className="space-y-5">
                            <div className="text-center space-y-1">
                                <p className="text-tg-text-secondary text-sm">กรอกรหัส 6 หลักจากแอป Authenticator</p>
                                <p className="text-tg-text-secondary text-xs">รหัสจะหมดอายุทุก 30 วินาที</p>
                            </div>

                            <OtpInput value={otp} onChange={setOtp} disabled={loading} autoFocus />

                            <AnimatePresence>
                                {error && (
                                    <motion.div
                                        initial={{ opacity: 0, height: 0 }}
                                        animate={{ opacity: 1, height: 'auto' }}
                                        exit={{ opacity: 0, height: 0 }}
                                        className="text-sm p-3 rounded-lg bg-red-500/20 text-red-400 text-center"
                                    >
                                        {error}
                                    </motion.div>
                                )}
                            </AnimatePresence>

                            <button type="submit" disabled={loading || otp.length !== 6} className="tg-button disabled:opacity-50">
                                {loading ? (
                                    <span className="flex items-center justify-center gap-2">
                                        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                        กำลังยืนยัน...
                                    </span>
                                ) : (
                                    <span className="flex items-center justify-center gap-2">
                                        <ShieldCheck size={16} /> ยืนยันและเข้าสู่ระบบ
                                    </span>
                                )}
                            </button>

                            <button
                                type="button"
                                onClick={() => setPhase('scan')}
                                className="w-full text-tg-text-secondary hover:text-white text-xs text-center py-1 transition-all"
                            >
                                ← กลับไปสแกน QR Code
                            </button>
                        </form>
                    </motion.div>
                )}
            </AnimatePresence>
        </motion.div>
    );
};

// ─────────────────────────────────────────
//  Sub-component: MFA Challenge Screen
// ─────────────────────────────────────────

interface MfaChallengeScreenProps {
    sessionToken: string;
    username: string;
    isAdaptive?: boolean;
    onSuccess: () => void;
    onBack: () => void;
}

const MfaChallengeScreen: React.FC<MfaChallengeScreenProps> = ({
    sessionToken, username, isAdaptive, onSuccess, onBack
}) => {
    const [otp, setOtp] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const doVerify = useCallback(async (code: string) => {
        setLoading(true);
        setError('');
        try {
            const res = await fetch('http://localhost:8000/api/auth/mfa/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: sessionToken, code }),
                // @ts-ignore
                credentials: 'include',
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'รหัสไม่ถูกต้อง');
            onSuccess();
        } catch (e: any) {
            setError(e.message);
            setOtp('');
        } finally {
            setLoading(false);
        }
    }, [sessionToken, onSuccess]);

    // Auto-submit เมื่อกรอกครบ 6 หลัก
    useEffect(() => {
        if (otp.length === 6 && !loading) {
            doVerify(otp);
        }
    }, [otp, loading, doVerify]);

    return (
        <motion.div
            key="mfa_challenge"
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -40 }}
            className="w-full"
        >
            <div className="flex items-center gap-3 mb-7">
                <button
                    onClick={onBack}
                    className="w-8 h-8 rounded-lg bg-white/5 hover:bg-white/10 flex items-center justify-center text-tg-text-secondary hover:text-white transition-all shrink-0"
                >
                    <ArrowLeft size={16} />
                </button>
                <div>
                    <h3 className="text-white font-bold text-lg leading-tight">ยืนยันตัวตน</h3>
                    <p className="text-tg-text-secondary text-xs mt-0.5">Two-Factor Authentication</p>
                </div>
            </div>

            <div className="flex justify-center mb-6">
                <div className="relative">
                    <div className="w-16 h-16 bg-tg-accent/15 rounded-2xl flex items-center justify-center border border-tg-accent/30">
                        <KeyRound size={28} className="text-tg-accent" />
                    </div>
                    {isAdaptive && (
                        <div className="absolute -top-1 -right-1 w-5 h-5 bg-amber-500 rounded-full flex items-center justify-center border-2 border-tg-sidebar">
                            <AlertTriangle size={10} className="text-black" />
                        </div>
                    )}
                </div>
            </div>

            {isAdaptive && (
                <div className="flex items-start gap-2.5 bg-amber-500/10 border border-amber-500/25 rounded-xl px-4 py-3 mb-5">
                    <AlertTriangle size={15} className="text-amber-400 shrink-0 mt-0.5" />
                    <p className="text-amber-300 text-xs leading-relaxed">
                        การเข้าสู่ระบบจาก <strong>อุปกรณ์ / เครือข่ายใหม่</strong> — ต้องยืนยัน 2FA
                    </p>
                </div>
            )}

            <div className="text-center mb-6 space-y-1">
                <p className="text-white font-medium">
                    สวัสดี, <span className="text-tg-accent">{username}</span>
                </p>
                <p className="text-tg-text-secondary text-sm">กรอกรหัส 6 หลักจากแอป Authenticator</p>
                <p className="text-tg-text-secondary text-xs opacity-60">รหัสจะถูกยืนยันอัตโนมัติเมื่อครบ 6 หลัก</p>
            </div>

            <div className="space-y-5">
                <OtpInput value={otp} onChange={setOtp} disabled={loading} autoFocus />

                <AnimatePresence>
                    {loading && (
                        <motion.div
                            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                            className="flex justify-center py-2"
                        >
                            <div className="flex items-center gap-2 text-tg-text-secondary text-sm">
                                <div className="w-4 h-4 border-2 border-tg-accent border-t-transparent rounded-full animate-spin" />
                                กำลังตรวจสอบ...
                            </div>
                        </motion.div>
                    )}
                    {error && (
                        <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: 'auto' }}
                            exit={{ opacity: 0, height: 0 }}
                            className="text-sm p-3 rounded-lg bg-red-500/20 text-red-400 text-center"
                        >
                            {error}
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>

            <p className="text-center mt-6 text-[11px] text-tg-text-secondary opacity-50 uppercase tracking-widest">
                Thai Stylometry · Adaptive Auth
            </p>
        </motion.div>
    );
};

// ─────────────────────────────────────────
//  Main Component: AuthScreen
// ─────────────────────────────────────────

/**
 * หน้าจอ Authentication สำหรับ Login และ Register
 * รองรับ MFA Flow:
 *   credentials → mfa_setup (QR + OTP) → /chat
 *   credentials → mfa_challenge (OTP only) → /chat
 */
const AuthScreen: React.FC = () => {
    const [isLogin, setIsLogin] = useState(true);
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const [step, setStep] = useState<AuthStep>('credentials');
    const [mfaSetupToken, setMfaSetupToken] = useState('');
    const [mfaSessionToken, setMfaSessionToken] = useState('');
    const [isAdaptiveMfa, setIsAdaptiveMfa] = useState(false);

    const setCurrentUser = useStore((state) => state.setCurrentUser);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError('');

        const endpoint = isLogin ? '/api/login' : '/api/register';

        try {
            const response = await fetch(`http://localhost:8000${endpoint}`, {
                method: 'POST',
                headers: {
                    'Content-Type': isLogin
                        ? 'application/x-www-form-urlencoded'
                        : 'application/json',
                },
                body: isLogin
                    ? new URLSearchParams({ username, password }).toString()
                    : JSON.stringify({ username, password }),
                // @ts-ignore
                credentials: 'include',
            });

            const data = await response.json();

            if (!response.ok) {
                setError(data.detail || 'เกิดข้อผิดพลาด กรุณาลองใหม่');
                return;
            }

            // ── Register ──
            if (!isLogin) {
                if (data.mfa_setup_required && data.setup_token) {
                    setMfaSetupToken(data.setup_token);
                    setIsAdaptiveMfa(false);
                    setStep('mfa_setup');
                } else {
                    setIsLogin(true);
                    setError('สมัครสมาชิกสำเร็จ! กรุณาเข้าสู่ระบบ');
                }
                return;
            }

            // ── Login ──
            if (data.mfa_required) {
                // Adaptive Auth: device ใหม่ ยังไม่มี MFA → Setup ก่อน
                if (data.mfa_enabled === false && data.setup_token) {
                    setMfaSetupToken(data.setup_token);
                    setIsAdaptiveMfa(true);
                    setStep('mfa_setup');
                    return;
                }
                // MFA เปิดอยู่แล้ว → Challenge
                if (data.session_token) {
                    setMfaSessionToken(data.session_token);
                    setIsAdaptiveMfa(!!data.adaptive_auth);
                    setStep('mfa_challenge');
                    return;
                }
            }

            // ── Login สำเร็จ ไม่ต้อง MFA ──
            setCurrentUser(username);
            window.location.href = '/chat';

        } catch {
            setError('ไม่สามารถเชื่อมต่อกับเซิร์ฟเวอร์ได้');
        } finally {
            setLoading(false);
        }
    };

    const handleMfaSuccess = useCallback(() => {
        setCurrentUser(username);
        window.location.href = '/chat';
    }, [username, setCurrentUser]);

    const handleBack = useCallback(() => {
        setStep('credentials');
        setMfaSetupToken('');
        setMfaSessionToken('');
        setIsAdaptiveMfa(false);
        setError('');
    }, []);

    return (
        <div className="min-h-screen flex items-center justify-center bg-tg-bg p-4">
            <motion.div
                layout
                className="max-w-md w-full bg-tg-sidebar shadow-2xl border border-tg-header rounded-2xl overflow-hidden"
            >
                <AnimatePresence mode="wait">

                    {step === 'mfa_setup' && (
                        <motion.div key="mfa_setup" className="p-8">
                            <MfaSetupScreen
                                setupToken={mfaSetupToken}
                                isAdaptive={isAdaptiveMfa}
                                username={username}
                                onSuccess={handleMfaSuccess}
                                onBack={handleBack}
                            />
                        </motion.div>
                    )}

                    {step === 'mfa_challenge' && (
                        <motion.div key="mfa_challenge" className="p-8">
                            <MfaChallengeScreen
                                sessionToken={mfaSessionToken}
                                username={username}
                                isAdaptive={isAdaptiveMfa}
                                onSuccess={handleMfaSuccess}
                                onBack={handleBack}
                            />
                        </motion.div>
                    )}

                    {step === 'credentials' && (
                        <motion.div
                            key="credentials"
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -20 }}
                            className="p-8"
                        >
                            {/* Logo */}
                            <div className="flex flex-col items-center mb-8">
                                <div className="w-20 h-20 bg-tg-accent rounded-full flex items-center justify-center mb-4 shadow-lg shadow-tg-accent/20">
                                    <motion.div layout transition={{ type: 'spring', stiffness: 300, damping: 20 }}>
                                        {isLogin
                                            ? <LogIn size={38} className="text-white" />
                                            : <UserPlus size={38} className="text-white" />}
                                    </motion.div>
                                </div>
                                <h2 className="text-2xl font-bold text-white">
                                    {isLogin ? 'ยินดีต้อนรับกลับมา' : 'สร้างบัญชีใหม่'}
                                </h2>
                                <p className="text-tg-text-secondary mt-1 text-sm">Thai Stylometry V2 Chat</p>
                            </div>

                            {/* Security badges */}
                            <div className="flex justify-center gap-2 mb-6">
                                <span className="flex items-center gap-1.5 text-[10px] text-tg-text-secondary bg-white/5 border border-white/8 px-2.5 py-1 rounded-full">
                                    <ShieldCheck size={10} className="text-tg-accent" /> 2FA Protected
                                </span>
                                <span className="flex items-center gap-1.5 text-[10px] text-tg-text-secondary bg-white/5 border border-white/8 px-2.5 py-1 rounded-full">
                                    <Lock size={10} className="text-green-400" /> HttpOnly Cookie
                                </span>
                            </div>

                            <form onSubmit={handleSubmit} className="space-y-4">
                                <div className="relative">
                                    <User className="absolute left-3 top-3.5 text-tg-text-secondary" size={18} />
                                    <input
                                        type="text"
                                        placeholder="Username"
                                        className="tg-input pl-10"
                                        value={username}
                                        onChange={(e) => setUsername(e.target.value)}
                                        required
                                        autoComplete="username"
                                    />
                                </div>

                                <div className="relative">
                                    <Lock className="absolute left-3 top-3.5 text-tg-text-secondary" size={18} />
                                    <input
                                        type={showPassword ? 'text' : 'password'}
                                        placeholder="Password"
                                        className="tg-input pl-10 pr-10"
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        required
                                        autoComplete={isLogin ? 'current-password' : 'new-password'}
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowPassword((v) => !v)}
                                        className="absolute right-3 top-3.5 text-tg-text-secondary hover:text-white transition-colors"
                                        tabIndex={-1}
                                    >
                                        {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                                    </button>
                                </div>

                                <AnimatePresence>
                                    {error && (
                                        <motion.div
                                            initial={{ opacity: 0, height: 0 }}
                                            animate={{ opacity: 1, height: 'auto' }}
                                            exit={{ opacity: 0, height: 0 }}
                                            className={`text-sm p-3 rounded-lg text-center ${
                                                error.includes('สำเร็จ')
                                                    ? 'bg-green-500/20 text-green-400'
                                                    : 'bg-red-500/20 text-red-400'
                                            }`}
                                        >
                                            {error}
                                        </motion.div>
                                    )}
                                </AnimatePresence>

                                <button type="submit" disabled={loading} className="tg-button mt-2 disabled:opacity-60">
                                    {loading ? (
                                        <span className="flex items-center justify-center gap-2">
                                            <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                            กำลังดำเนินการ...
                                        </span>
                                    ) : (
                                        isLogin ? 'เข้าสู่ระบบ' : 'สมัครสมาชิก'
                                    )}
                                </button>
                            </form>

                            <div className="mt-6 text-center">
                                <button
                                    onClick={() => { setIsLogin(!isLogin); setError(''); }}
                                    className="text-tg-accent hover:underline text-sm font-medium"
                                >
                                    {isLogin ? 'ยังไม่มีบัญชี? สมัครที่นี่' : 'มีบัญชีอยู่แล้ว? เข้าสู่ระบบ'}
                                </button>
                            </div>
                        </motion.div>
                    )}

                </AnimatePresence>
            </motion.div>
        </div>
    );
};

export default AuthScreen;
