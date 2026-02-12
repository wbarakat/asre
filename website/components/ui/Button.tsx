"use client";

import React from "react";
import Link from "next/link";
import { cn } from "@/lib/cn";

type ButtonVariant = "primary" | "secondary";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonBaseProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
  children: React.ReactNode;
}

interface ButtonAsLink extends ButtonBaseProps {
  href: string;
  onClick?: never;
  type?: never;
  disabled?: never;
}

interface ButtonAsButton extends ButtonBaseProps {
  href?: never;
  onClick?: React.MouseEventHandler<HTMLButtonElement>;
  type?: "button" | "submit" | "reset";
  disabled?: boolean;
}

type ButtonProps = ButtonAsLink | ButtonAsButton;

const variantStyles: Record<ButtonVariant, string> = {
  primary: cn(
    "bg-white text-black",
    "hover:bg-white/90",
    "active:bg-white/80",
    "shadow-sm hover:shadow-md",
    "rounded-full",
  ),
  secondary: cn(
    "border border-white/30 text-white/90",
    "hover:border-white/50 hover:text-white",
    "active:bg-white/5",
    "rounded-full",
  ),
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "px-5 py-2.5 text-sm min-h-[40px]",
  md: "px-6 py-3 text-base min-h-[44px]",
  lg: "px-8 py-3.5 text-lg min-h-[48px]",
};

export default function Button({
  variant = "primary",
  size = "md",
  className,
  children,
  ...props
}: ButtonProps) {
  const classes = cn(
    "inline-flex items-center justify-center font-medium transition-all duration-200",
    variantStyles[variant],
    sizeStyles[size],
    className,
  );

  if ("href" in props && props.href) {
    return (
      <Link href={props.href} className={classes}>
        {children}
      </Link>
    );
  }

  const { onClick, type = "button", disabled } = props as ButtonAsButton;

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={cn(classes, disabled && "opacity-50 cursor-not-allowed pointer-events-none")}
    >
      {children}
    </button>
  );
}
