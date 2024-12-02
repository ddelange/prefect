import { Slot } from "@radix-ui/react-slot";
import type { VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";
import { buttonVariants } from "./styles";
import { Loader2 } from "lucide-react";

export interface ButtonProps
	extends React.ButtonHTMLAttributes<HTMLButtonElement>,
		VariantProps<typeof buttonVariants> {
	asChild?: boolean;
	loading?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
	(
		{
			className,
			variant,
			size,
			asChild = false,
			loading = false,
			children,
			...props
		},
		ref,
	) => {
		const Comp = asChild ? Slot : "button";

		return (
			<Comp
				className={cn(buttonVariants({ variant, size, className }))}
				ref={ref}
				disabled={loading}
				{...props}
			>
				{loading ? <Loader2 className="w-4 h-4 animate-spin" /> : children}
			</Comp>
		);
	},
);
Button.displayName = "Button";

export { Button };