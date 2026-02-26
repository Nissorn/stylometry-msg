import React, { useState } from 'react';
import { useStore } from '../../store/useStore';
import { motion, AnimatePresence } from 'framer-motion';
import { Lock, User, LogIn, UserPlus } from 'lucide-react';

/**
 * หน้าจอ Authentication สำหรับ Login และ Register
 * ออกแบบให้คล้าย Telegram Desktop พร้อม Animation
 */
const AuthScreen: React.FC = () => {
    const [isLogin, setIsLogin] = useState(true);
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const setCurrentUser = useStore((state) => state.setCurrentUser);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError('');

        const endpoint = isLogin ? '/api/login' : '/api/register';

        try {
            // 📌 สำคัญ: ต้องใช้ credentials: 'include' เพื่อให้ Browser รับ-ส่ง HTTP-Only Cookie
            const response = await fetch(`http://localhost:8000${endpoint}`, {
                method: 'POST',
                headers: {
                    'Content-Type': isLogin ? 'application/x-www-form-urlencoded' : 'application/json',
                },
                body: isLogin
                    ? new URLSearchParams({ username, password }).toString()
                    : JSON.stringify({ username, password }),
                // @ts-ignore
                credentials: 'include',
            });

            const data = await response.json();

            if (response.ok) {
                if (isLogin) {
                    setCurrentUser(username);
                    window.location.href = '/chat';
                } else {
                    // ถ้าสมัครสำเร็จ ให้สลับมาหน้า Login
                    setIsLogin(true);
                    setError('สมัครสมาชิกสำเร็จ! กรุณาเข้าสู่ระบบ');
                }
            } else {
                setError(data.detail || 'เกิดข้อผิดพลาด กรุณาลองใหม่');
            }
        } catch (err) {
            setError('ไม่สามารถเชื่อมต่อกับเซิร์ฟเวอร์ได้');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-tg-bg p-4">
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="max-w-md w-full bg-tg-sidebar p-8 rounded-2xl shadow-2xl border border-tg-header"
            >
                <div className="flex flex-col items-center mb-8">
                    <div className="w-20 h-20 bg-tg-accent rounded-full flex items-center justify-center mb-4 shadow-lg">
                        <motion.div
                            layout
                            transition={{ type: "spring", stiffness: 300, damping: 20 }}
                        >
                            {isLogin ? <LogIn size={40} className="text-white" /> : <UserPlus size={40} className="text-white" />}
                        </motion.div>
                    </div>
                    <h2 className="text-2xl font-bold text-white">
                        {isLogin ? 'ยินดีต้อนรับกลับมา' : 'สร้างบัญชีใหม่'}
                    </h2>
                    <p className="text-tg-text-secondary mt-2">
                        Thai Stylometry V2 Chat
                    </p>
                </div>

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="relative">
                        <User className="absolute left-3 top-3 text-tg-text-secondary" size={20} />
                        <input
                            type="text"
                            placeholder="Username"
                            className="tg-input pl-10"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            required
                        />
                    </div>
                    <div className="relative">
                        <Lock className="absolute left-3 top-3 text-tg-text-secondary" size={20} />
                        <input
                            type="password"
                            placeholder="Password"
                            className="tg-input pl-10"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                        />
                    </div>

                    <AnimatePresence>
                        {error && (
                            <motion.div
                                initial={{ opacity: 0, height: 0 }}
                                animate={{ opacity: 1, height: 'auto' }}
                                exit={{ opacity: 0, height: 0 }}
                                className={`text-sm p-3 rounded-lg ${error.includes('สำเร็จ') ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}
                            >
                                {error}
                            </motion.div>
                        )}
                    </AnimatePresence>

                    <button
                        type="submit"
                        disabled={loading}
                        className="tg-button mt-4"
                    >
                        {loading ? 'กำลังดำเนินการ...' : (isLogin ? 'เข้าสู่ระบบ' : 'สมัครสมาชิก')}
                    </button>
                </form>

                <div className="mt-6 text-center">
                    <button
                        onClick={() => setIsLogin(!isLogin)}
                        className="text-tg-accent hover:underline text-sm font-medium"
                    >
                        {isLogin ? 'ยังไม่มีบัญชี? สมัครที่นี่' : 'มีบัญชีอยู่แล้ว? เข้าสู่ระบบ'}
                    </button>
                </div>
            </motion.div>
        </div>
    );
};

export default AuthScreen;
