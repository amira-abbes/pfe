import React from "react";

export default function AuthTriangles() {
  return (
    <div className="auth-triangles-container" style={{
      position: "fixed",
      top: 0,
      left: 0,
      width: "100%",
      height: "100%",
      zIndex: -1,
      overflow: "hidden",
      pointerEvents: "none",
      background: "linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%)"
    }}>
      <div style={{
        position: "absolute",
        top: "-10%",
        right: "-5%",
        width: "40vw",
        height: "40vw",
        background: "linear-gradient(135deg, rgba(0, 102, 179, 0.1) 0%, rgba(0, 102, 179, 0.05) 100%)",
        clipPath: "polygon(50% 0%, 0% 100%, 100% 100%)",
        transform: "rotate(15deg)",
        filter: "blur(40px)"
      }} />
      <div style={{
        position: "absolute",
        bottom: "-5%",
        left: "-5%",
        width: "30vw",
        height: "30vw",
        background: "linear-gradient(135deg, rgba(0, 102, 179, 0.08) 0%, rgba(0, 102, 179, 0.03) 100%)",
        clipPath: "polygon(50% 0%, 0% 100%, 100% 100%)",
        transform: "rotate(-20deg)",
        filter: "blur(30px)"
      }} />
    </div>
  );
}
