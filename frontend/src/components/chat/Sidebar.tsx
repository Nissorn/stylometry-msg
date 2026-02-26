import React, { useState, useEffect } from 'react';
import { useStore } from '../../store/useStore';
import { Search, UserPlus, MoreVertical, User, LogOut } from 'lucide-react';
import { motion } from 'framer-motion';

/**
 * Sidebar สำหรับค้นหาเพื่อนและแสดงรายชื่อผู้ติดต่อ
 */
const Sidebar: React.FC = () => {
    const [searchQuery, setSearchQuery] = useState('');
    const [searchResults, setSearchResults] = useState<string[]>([]);
    const { currentUser, contacts, setContacts, activeContact, setActiveContact, clearStore } = useStore();
    const [isLoggingOut, setIsLoggingOut] = useState(false);

    // ดึงรายชื่อผู้ติดต่อเมื่อโหลดหน้าจอ
    useEffect(() => {
        fetchContacts();

        // 📌 รับ event ให้ดึงรายชื่อเพื่อนใหม่ (เช่น ตอนมีคนแอดมา)
        const handleRefresh = () => fetchContacts();
        window.addEventListener('refresh-contacts', handleRefresh);
        return () => window.removeEventListener('refresh-contacts', handleRefresh);
    }, []);

    const fetchContacts = async () => {
        try {
            const response = await fetch('http://localhost:8000/api/contacts/list', {
                // @ts-ignore
                credentials: 'include'
            });
            const data = await response.json();
            if (response.ok) {
                setContacts(data.contacts);
            }
        } catch (err) {
            console.error('Failed to fetch contacts', err);
        }
    };

    const handleSearch = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const query = e.target.value;
        setSearchQuery(query);
        if (query.length > 1) {
            try {
                const response = await fetch(`http://localhost:8000/api/contacts/search/${query}`, {
                    // @ts-ignore
                    credentials: 'include'
                });
                const data = await response.json();
                setSearchResults(data.results);
            } catch (err) {
                console.error('Search failed', err);
            }
        } else {
            setSearchResults([]);
        }
    };

    const addContact = async (username: string) => {
        try {
            const response = await fetch('http://localhost:8000/api/contacts/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ contact_username: username }),
                // @ts-ignore
                credentials: 'include'
            });
            if (response.ok) {
                fetchContacts();
                setSearchQuery('');
                setSearchResults([]);
            }
        } catch (err) {
            console.error('Add contact failed', err);
        }
    };

    /**
     * ฟังก์ชัน Logout
     * ล้างข้อมูล Session ใน Backend และเคลียร์ State ทั้งหมดใน Frontend
     */
    const handleLogout = async () => {
        setIsLoggingOut(true);
        try {
            const response = await fetch('http://localhost:8000/api/logout', {
                method: 'POST',
                // 📌 สำคัญ: ส่ง credentials ไปด้วยเพื่อให้ Backend รู้ว่าต้องไปล้าง HttpOnly Cookie ตัวไหน
                // @ts-ignore
                credentials: 'include'
            });

            if (response.ok) {
                // เคลียร์ข้อมูลทุกอย่างใน Zustand Store (user, contacts, messages, security)
                clearStore();
                // บังคับเปลี่ยนหน้าไป Login
                window.location.href = '/login';
            }
        } catch (err) {
            console.error('Logout failed', err);
            setIsLoggingOut(false);
        }
    };

    return (
        <div className="w-[300px] border-r border-tg-header flex flex-col bg-tg-sidebar shrink-0 relative">

            {/* 📌 1. User Profile Section (Top) */}
            <div className="p-4 border-b border-[#0f1721] bg-tg-header/50 flex flex-col gap-3">
                <div className="flex flex-row items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="w-12 h-12 bg-tg-accent rounded-full flex items-center justify-center font-bold text-white shadow-lg text-lg">
                            {currentUser ? currentUser[0].toUpperCase() : <User />}
                        </div>
                        <div className="flex flex-col">
                            <span className="font-bold text-white leading-tight">
                                {currentUser || 'Loading...'}
                            </span>
                            <span className="text-xs text-green-400 flex items-center gap-1 mt-0.5">
                                <span className="w-1.5 h-1.5 rounded-full bg-green-400"></span>
                                Online
                            </span>
                        </div>
                    </div>
                </div>

                <div className="flex gap-2.5">
                    <button className="flex-1 bg-tg-header py-1.5 rounded-lg text-tg-text-secondary hover:text-white hover:bg-tg-accent/20 transition-all flex items-center justify-center text-xs font-medium border border-white/5">
                        <User size={14} className="mr-1.5" /> Profiles
                    </button>
                    <button
                        onClick={handleLogout}
                        disabled={isLoggingOut}
                        className="bg-red-500/10 hover:bg-red-500/20 text-red-500 py-1.5 px-3 rounded-lg transition-all flex items-center justify-center text-xs font-medium border border-red-500/20 disabled:opacity-50"
                        title="Logout"
                    >
                        {isLoggingOut ? (
                            <div className="w-3.5 h-3.5 border-2 border-red-500 border-t-transparent rounded-full animate-spin"></div>
                        ) : (
                            <>
                                <LogOut size={14} className="mr-1.5" /> ออกจากระบบ
                            </>
                        )}
                    </button>
                </div>
            </div>

            {/* Sidebar Search Header */}
            <div className="p-4 flex items-center gap-3 bg-tg-sidebar">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-2.5 text-tg-text-secondary" size={16} />
                    <input
                        type="text"
                        placeholder="ค้นหา..."
                        className="w-full bg-tg-header rounded-full py-2 pl-10 pr-4 text-sm outline-none focus:ring-1 focus:ring-tg-accent transition-all"
                        value={searchQuery}
                        onChange={handleSearch}
                    />
                </div>
            </div>

            {/* Results / List */}
            <div className="flex-1 overflow-y-auto">
                {searchQuery.length > 0 ? (
                    <div className="p-2">
                        <h3 className="text-xs font-semibold text-tg-text-secondary px-3 py-2 uppercase tracking-wider">
                            ผลการค้นหา
                        </h3>
                        {searchResults.map((user) => (
                            <div
                                key={user}
                                className="sidebar-item group"
                                onClick={() => addContact(user)}
                            >
                                <div className="w-10 h-10 bg-tg-header rounded-full flex items-center justify-center mr-3 group-hover:bg-tg-accent transition-colors">
                                    <User size={20} />
                                </div>
                                <div className="flex-1">
                                    <div className="font-medium text-white">{user}</div>
                                    <div className="text-xs text-tg-accent">คลิกเพื่อเพิ่มเพื่อน</div>
                                </div>
                                <UserPlus size={16} className="text-tg-text-secondary opacity-0 group-hover:opacity-100 transition-opacity" />
                            </div>
                        ))}
                        {searchResults.length === 0 && searchQuery.length > 1 && (
                            <div className="text-center py-4 text-tg-text-secondary text-sm">ไม่พบผู้ใช้</div>
                        )}
                    </div>
                ) : (
                    <div className="p-2">
                        <h3 className="text-xs font-semibold text-tg-text-secondary px-3 py-2 uppercase tracking-wider">
                            แชทล่าสุด
                        </h3>
                        {contacts.map((contact) => (
                            <motion.div
                                key={contact}
                                whileHover={{ scale: 1.02 }}
                                whileTap={{ scale: 0.98 }}
                                className={`sidebar-item ${activeContact === contact ? 'active' : ''}`}
                                onClick={() => setActiveContact(contact)}
                            >
                                <div className={`w-12 h-12 rounded-full flex items-center justify-center mr-3 ${activeContact === contact ? 'bg-white/20' : 'bg-tg-header'}`}>
                                    <User size={24} />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="font-medium text-white truncate">{contact}</div>
                                    <div className={`text-xs truncate ${activeContact === contact ? 'text-white/70' : 'text-tg-text-secondary'}`}>
                                        แตะเพื่อเริ่มคุย
                                    </div>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

export default Sidebar;
