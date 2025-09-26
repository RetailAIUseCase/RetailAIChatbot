import * as React from "react";
import logoDark from "@/public/nagarrologodark.svg";
import { cn } from "@/lib/utils";
import Image from "next/image";

function Header({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="header"
      className={cn(
        "text-background flex items-center justify-between gap-6 py-6 px-6",
        className
      )}
      {...props}
    >
      {/* Left Side Title */}
      <h1 className="text-4xl font-bold tracking-tight">SCIA</h1>

      {/* Right Side Logo */}
      <Image
        alt="Nagarro Logo"
        src={logoDark}
        height={40}
        width={128}
        className="h-[40px] w-auto"
      />
    </div>
  );
}

export { Header };