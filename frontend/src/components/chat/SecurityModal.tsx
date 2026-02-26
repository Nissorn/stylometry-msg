import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { ShieldAlert, ShieldCheck, Lock } from 'lucide-react';
import { useStore } from '../../store/useStore';

/**
 * Modal สำหรับปลดล็อคหน้าจอ (The Freeze Action)
 */
const SecurityModal: React.FC = () => {
    const [pin, setPin] = useState('');
    const [isVerifying, setIsVerifying] = useState(false);
    const [error, setError] = useState('');
    const updateSecurity = useStore((state) => state.updateSecurity);

    const handleUnfreeze = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsVerifying(true);
        setError('');

        // 📌 จำลองการยืนยันตัวตน (ในระบบจริงต้องยิง API ไปเช็ค password/pin)
        setTimeout(() => {
            if (pin === '1234' || pin.length >= 4) {
                updateSecurity({ isFrozen: false, trustScore: 1.0, messageWindow: 0 });
            } else {
                setError('รหัสยืนยันไม่ถูกต้อง กรุณาลองอีกครั้ง');
            }
            setIsVerifying(false);
        }, 1500);
    };

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
            <motion.div
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                className="max-w-md w-full bg-tg-sidebar p-8 rounded-3xl border border-red-500/30 shadow-[0_0_50px_rgba(239,68,68,0.2)] text-center"
            >
                <div className="w-20 h-20 bg-red-500 rounded-full flex items-center justify-center mx-auto mb-6 shadow-lg shadow-red-500/20">
                    <ShieldAlert size={40} className="text-white" />
                </div>

                <h2 className="text-2xl font-bold text-white mb-2">SECURITY FREEZE</h2>
                <p className="text-tg-text-secondary text-sm mb-8">
                    ระบบตรวจพบพฤติกรรมการพิมพ์ที่ไม่คุ้นเคย
                    เพื่อความปลอดภัย กรุณายืนยันตัวตนเจ้าของบัญชี
                </p>

                <form onSubmit={handleUnfreeze} className="space-y-4">
                    <div className="relative">
                        <Lock className="absolute left-4 top-3.5 text-tg-text-secondary" size={20} />
                        <input
                            type="password"
                            placeholder="กรอกรหัส PIN หรือ Password"
                            className="w-full bg-tg-header border-2 border-transparent focus:border-tg-accent rounded-xl py-3 pl-12 pr-4 text-white outline-none transition-all placeholder:text-tg-text-secondary"
                            value={pin}
                            onChange={(e) => setPin(e.target.value)}
                            autoFocus
                            required
                        />
                    </div>

                    {error && (
                        <motion.p
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="text-red-400 text-xs"
                        >
                            {error}
                        </motion.p>
                    )}

                    <button
                        type="submit"
                        disabled={isVerifying}
                        className="w-full bg-white text-black font-bold py-3 rounded-xl hover:bg-gray-200 transition-all flex items-center justify-center gap-2 group"
                    >
                        {isVerifying ? (
                            <span className="flex items-center gap-2">
                                <div className="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin" />
                                กำลังตรวจสอบ...
                            </span>
                        ) : (
                            <>
                                <ShieldCheck size={20} />
                                ยืนยันตัวตนปลดล็อค
                            </>
                        )}
                    </button>
                </form>

                <p className="mt-8 text-[10px] text-tg-text-secondary uppercase tracking-widest">
                    Thai Stylometry Protection Layer Active
                </p>
            </motion.div>
        </div>
    );
};

export default SecurityModal;
