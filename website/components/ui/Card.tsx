import React from "react";
import { cn } from "@/lib/cn";

interface CardProps {
  className?: string;
  children: React.ReactNode;
  accent?: boolean;
  onClick?: React.MouseEventHandler<HTMLDivElement>;
}

export default function Card({ className, children, accent = false, onClick }: CardProps) {
  return (
    <div
      className={cn(
        accent ? "card-glass" : "card-dark",
        "p-6 md:p-8",
        onClick && "cursor-pointer",
        className,
      )}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e: React.KeyboardEvent<HTMLDivElement>) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick(e as unknown as React.MouseEvent<HTMLDivElement>);
              }
            }
          : undefined
      }
    >
      {children}
    </div>
  );
}
