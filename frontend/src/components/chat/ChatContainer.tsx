import React, { useEffect } from 'react';
import Sidebar from './Sidebar.tsx';
import ChatWindow from './ChatWindow.tsx';
import SecurityDashboard from './SecurityDashboard.tsx';
import SecurityModal from './SecurityModal.tsx';
import { useStore } from '../../store/useStore';

/**
 * Main Layout สำหรับหน้า Chat (3 Columns)
 */
const ChatContainer: React.FC = () => {
    const { currentUser, setCurrentUser } = useStore();
    const isFrozen = useStore((state) => state.security.isFrozen);
    const [isLoading, setIsLoading] = React.useState(true);

    // ตรวจสอบสถานะการ Login ผ่าน /api/me ทันทีที่โหลดหน้าจอ
    useEffect(() => {
        const checkAuthStatus = async () => {
            try {
                const response = await fetch('http://localhost:8000/api/me', {
                    // 📌 credentials: 'include' สำคัญมาก: เพื่อให้ Browser โหลดและแนบ HttpOnly Cookie 
                    // (ที่เก็บ JWT) ส่งไปพร้อมกับ Request นี้อัตโนมัติ 
                    // หากไม่ใส่ Backend จะไม่ได้ Cookie และจะปฏิเสธการเชื่อมต่อ (401)
                    // @ts-ignore
                    credentials: 'include'
                });

                if (response.ok) {
                    const data = await response.json();
                    setCurrentUser(data.username);
                    setIsLoading(false);
                } else {
                    // ถ้าไม่สำเร็จ (เช่น 401 โทเค็นหมดอายุ หรือไม่มี Cookie) เตะออกไปหน้า Login
                    window.location.href = '/login';
                }
            } catch (error) {
                console.error('Auth check failed:', error);
                window.location.href = '/login';
            }
        };

        checkAuthStatus();
    }, [setCurrentUser]);

    if (isLoading) {
        return (
            <div className="flex h-screen w-screen items-center justify-center bg-tg-bg text-white flex-col space-y-4">
                <div className="w-12 h-12 border-4 border-tg-header border-t-tg-accent rounded-full animate-spin"></div>
                <p className="text-tg-text-secondary font-medium animate-pulse">กำลังตรวจสอบสิทธิ์...</p>
            </div>
        );
    }

    return (
        <div className="flex h-screen w-screen bg-tg-bg overflow-hidden relative">
            {/* 1. Sidebar (Left) */}
            <Sidebar />

            {/* 2. Chat Window (Center) */}
            <ChatWindow />

            {/* 3. Security Dashboard (Right) */}
            <SecurityDashboard />

            {/* 4. Security Toggle / The Freeze Action Overlay */}
            {isFrozen && <SecurityModal />}
        </div>
    );
};

export default ChatContainer;
