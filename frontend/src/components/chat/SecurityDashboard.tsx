import React from 'react';
import { useStore } from '../../store/useStore';
import {
    Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer,
    PieChart, Pie, Cell
} from 'recharts';
import { Shield, AlertTriangle, CheckCircle, Activity } from 'lucide-react';

/**
 * Security Dashboard (Right Column)
 * แสดงคะแนนความน่าจะเป็นและพฤติกรรมการพิมพ์ (Meta-stats)
 */
const SecurityDashboard: React.FC = () => {
    const { security } = useStore();
    const { trustScore, messageWindow, currentMeta, ownerBaseline } = security;

    // ข้อมูลสำหรับ Radar Chart
    const radarData = [
        { subject: 'Length', A: currentMeta.length, B: ownerBaseline.length, fullMark: 100 },
        { subject: 'Giggles', A: currentMeta.giggles, B: ownerBaseline.giggles, fullMark: 100 },
        { subject: 'Elongation', A: currentMeta.elongation, B: ownerBaseline.elongation, fullMark: 100 },
        { subject: 'Punctuation', A: currentMeta.punctuation, B: ownerBaseline.punctuation, fullMark: 100 },
        { subject: 'Spacing', A: currentMeta.spacing, B: ownerBaseline.spacing, fullMark: 100 },
    ];

    // ข้อมูลสำหรับ Gauge (Trust Score)
    const gaugeData = [
        { name: 'Trust', value: trustScore * 100 },
        { name: 'Remaining', value: 100 - (trustScore * 100) },
    ];

    const getStatusColor = () => {
        if (trustScore >= 0.95) return '#4ade80'; // Green
        if (trustScore >= 0.80) return '#fbbf24'; // Yellow
        return '#f87171'; // Red
    };

    return (
        <div className="w-[350px] bg-tg-sidebar border-l border-tg-header flex flex-col shrink-0 p-6 overflow-y-auto">
            <div className="flex items-center gap-2 mb-8">
                <Shield className="text-tg-accent" size={24} />
                <h2 className="text-xl font-bold text-white uppercase tracking-tight">Security Panel</h2>
            </div>

            {/* Trust Score Gauge */}
            <div className="bg-tg-header rounded-2xl p-6 mb-6 flex flex-col items-center relative overflow-hidden">
                <div className="text-xs font-semibold text-tg-text-secondary uppercase mb-2">Trust Probability</div>
                <div className="h-40 w-full flex items-center justify-center relative">
                    <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                            <Pie
                                data={gaugeData}
                                cx="50%"
                                cy="100%"
                                startAngle={180}
                                endAngle={0}
                                innerRadius={60}
                                outerRadius={80}
                                paddingAngle={0}
                                dataKey="value"
                            >
                                <Cell fill={getStatusColor()} />
                                <Cell fill="#0f1721" />
                            </Pie>
                        </PieChart>
                    </ResponsiveContainer>
                    <div className="absolute bottom-2 text-3xl font-bold text-white">
                        {(trustScore * 100).toFixed(1)}%
                    </div>
                </div>
                <div className="flex items-center gap-2 mt-4">
                    {trustScore >= 0.95 ? (
                        <CheckCircle size={14} className="text-green-400" />
                    ) : (
                        <AlertTriangle size={14} className="text-amber-400" />
                    )}
                    <span className="text-xs font-medium" style={{ color: getStatusColor() }}>
                        {trustScore >= 0.95 ? 'IDENTITY VERIFIED' : 'IDENTITY SUSPICIOUS'}
                    </span>
                </div>
            </div>

            {/* 5-Message Window Status */}
            <div className="bg-tg-header rounded-2xl p-5 mb-6">
                <div className="flex justify-between items-center mb-4">
                    <div className="text-xs font-semibold text-tg-text-secondary uppercase">Analysis Window</div>
                    <Activity size={14} className="text-tg-accent" />
                </div>
                <div className="flex gap-2">
                    {[1, 2, 3, 4, 5].map((i) => (
                        <div
                            key={i}
                            className={`flex-1 h-2 rounded-full transition-all duration-500 ${i <= messageWindow ? 'bg-tg-accent shadow-[0_0_8px_rgba(82,136,193,0.5)]' : 'bg-tg-bg'
                                }`}
                        />
                    ))}
                </div>
                <div className="mt-3 text-[11px] text-tg-text-secondary text-center italic">
                    AI checks every 5 owner's messages
                </div>
            </div>

            {/* Meta-stats Radar Chart */}
            <div className="bg-tg-header rounded-2xl p-5 flex-1 min-h-[300px] flex flex-col">
                <div className="text-xs font-semibold text-tg-text-secondary uppercase mb-6">Typing Stylometry</div>
                <div className="flex-1 min-h-[220px]">
                    <ResponsiveContainer width="100%" height="100%">
                        <RadarChart cx="50%" cy="50%" outerRadius="70%" data={radarData}>
                            <PolarGrid stroke="#242f3d" />
                            <PolarAngleAxis dataKey="subject" tick={{ fill: '#708499', fontSize: 10 }} />
                            <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                            <Radar
                                name="Current Session"
                                dataKey="A"
                                stroke="#5288c1"
                                fill="#5288c1"
                                fillOpacity={0.6}
                            />
                            <Radar
                                name="Owner's Baseline"
                                dataKey="B"
                                stroke="#4ade80"
                                strokeDasharray="3 3"
                                fill="none"
                            />
                        </RadarChart>
                    </ResponsiveContainer>
                </div>
                <div className="flex justify-center gap-4 mt-2">
                    <div className="flex items-center gap-1.5 text-[10px] text-tg-text-secondary">
                        <span className="w-2 h-2 rounded-full bg-tg-accent" /> Session
                    </div>
                    <div className="flex items-center gap-1.5 text-[10px] text-tg-text-secondary">
                        <span className="w-2 h-2 rounded-full border border-green-400" /> Owner
                    </div>
                </div>
            </div>
        </div>
    );
};

export default SecurityDashboard;
