import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "@/components/ui/button";

describe("Button", () => {
  it("renders a native button by default", () => {
    render(<Button variant="secondary">Click</Button>);

    expect(screen.getByRole("button", { name: "Click" })).toBeInTheDocument();
  });

  it("renders as a child element when asChild is set", () => {
    render(
      <Button asChild>
        <a href="/x">Link</a>
      </Button>,
    );

    const link = screen.getByRole("link", { name: "Link" });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("data-slot", "button");
  });
});
