import { useEffect, useRef } from "react";

const DEFAULT_LENGTH = 6;

export default function OtpInput({
  value,
  onChange,
  length = DEFAULT_LENGTH,
  autoFocus = false,
  disabled = false,
  ariaLabel = "Code de verification",
}) {
  const inputsRef = useRef([]);
  const digits = Array.from({ length }, (_, index) => value[index] || "");

  useEffect(() => {
    if (!autoFocus || disabled) return;
    const timer = window.setTimeout(() => inputsRef.current[0]?.focus(), 80);
    return () => window.clearTimeout(timer);
  }, [autoFocus, disabled]);

  function commit(nextDigits, focusIndex = null) {
    onChange(nextDigits.join("").slice(0, length));
    if (focusIndex !== null) {
      window.setTimeout(() => inputsRef.current[focusIndex]?.focus(), 0);
    }
  }

  function handleChange(index, inputValue) {
    const clean = inputValue.replace(/\D/g, "");
    if (!clean) {
      const next = [...digits];
      next[index] = "";
      commit(next);
      return;
    }

    if (clean.length > 1) {
      handlePasteValue(clean, index);
      return;
    }

    const next = [...digits];
    next[index] = clean;
    commit(next, Math.min(index + 1, length - 1));
  }

  function handlePasteValue(rawValue, startIndex = 0) {
    const clean = rawValue.replace(/\D/g, "").slice(0, length);
    if (!clean) return;

    const next = [...digits];
    clean.split("").forEach((digit, offset) => {
      const targetIndex = startIndex + offset;
      if (targetIndex < length) next[targetIndex] = digit;
    });

    commit(next, Math.min(startIndex + clean.length, length - 1));
  }

  function handleKeyDown(index, event) {
    if (event.key === "Backspace") {
      event.preventDefault();
      const next = [...digits];

      if (next[index]) {
        next[index] = "";
        commit(next);
        return;
      }

      const previousIndex = Math.max(index - 1, 0);
      next[previousIndex] = "";
      commit(next, previousIndex);
      return;
    }

    if (event.key === "ArrowLeft") {
      event.preventDefault();
      inputsRef.current[Math.max(index - 1, 0)]?.focus();
      return;
    }

    if (event.key === "ArrowRight") {
      event.preventDefault();
      inputsRef.current[Math.min(index + 1, length - 1)]?.focus();
    }
  }

  return (
    <div className="otp-input-group" role="group" aria-label={ariaLabel}>
      {digits.map((digit, index) => (
        <input
          key={index}
          ref={(node) => {
            inputsRef.current[index] = node;
          }}
          className="otp-input"
          type="text"
          inputMode="numeric"
          autoComplete={index === 0 ? "one-time-code" : "off"}
          pattern="[0-9]*"
          maxLength={1}
          value={digit}
          disabled={disabled}
          aria-label={`${ariaLabel} - chiffre ${index + 1}`}
          onChange={(event) => handleChange(index, event.target.value)}
          onKeyDown={(event) => handleKeyDown(index, event)}
          onPaste={(event) => {
            event.preventDefault();
            handlePasteValue(event.clipboardData.getData("text"), index);
          }}
        />
      ))}
    </div>
  );
}
