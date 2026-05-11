import React, { useMemo } from "react";

const COLORS = [
  "#ff69b4", // pink
  "#ffd700", // yellow
  "#20b2aa", // teal
  "#9370db", // purple
  "#ffa500", // orange
  "#4169e1", // blue
  "#32cd32", // green
];

export default function AuthTriangles() {
  const triangles = useMemo(() => {
    return Array.from({ length: 18 }).map((_, i) => {
      const size = Math.random() * 80 + 20;
      const x = Math.random() * 100;
      const y = Math.random() * 100;
      const rotate = Math.random() * 360;
      const color = COLORS[Math.floor(Math.random() * COLORS.length)];
      const opacity = Math.random() * 0.4 + 0.1;
      const delay = Math.random() * 2;
      const isRainbow = Math.random() > 0.8;

      return { i, size, x, y, rotate, color, opacity, delay, isRainbow };
    });
  }, []);

  return (
    <div className="auth-triangles-container" style={{
      position: "fixed",
      top: 0,
      left: 0,
      width: "100%",
      height: "100%",
      zIndex: 0,
      overflow: "hidden",
      pointerEvents: "none",
    }}>
      {triangles.map((t) => (
        <div
          key={t.i}
          style={{
            position: "absolute",
            top: `${t.y}%`,
            left: `${t.x}%`,
            width: `${t.size}px`,
            height: `${t.size}px`,
            background: t.isRainbow 
              ? "linear-gradient(45deg, #ff00ff, #00ffff, #ffff00)" 
              : t.color,
            clipPath: "polygon(50% 0%, 0% 100%, 100% 100%)",
            transform: `rotate(${t.rotate}deg)`,
            opacity: t.opacity,
            filter: t.isRainbow ? "blur(2px) saturate(2)" : "none",
            animation: `float ${Math.random() * 10 + 10}s infinite ease-in-out`,
            animationDelay: `${t.delay}s`,
          }}
        />
      ))}
      <style>{`
        @keyframes float {
          0%, 100% { transform: translateY(0) rotate(0deg); }
          50% { transform: translateY(-20px) rotate(10deg); }
        }
      `}</style>
    </div>
  );
}
