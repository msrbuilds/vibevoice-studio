import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfirmProvider, useConfirm } from "./ConfirmProvider";

function Harness({ onResult }: { onResult: (v: boolean) => void }) {
  const confirm = useConfirm();
  return (
    <button
      onClick={async () => {
        const ok = await confirm({ title: "Delete?", message: "Sure?" });
        onResult(ok);
      }}
    >
      trigger
    </button>
  );
}

function setup() {
  const results: boolean[] = [];
  render(
    <ConfirmProvider isDark={false}>
      <Harness onResult={(v) => results.push(v)} />
    </ConfirmProvider>,
  );
  return results;
}

describe("useConfirm", () => {
  it("resolves true when the confirm button is clicked", async () => {
    const user = userEvent.setup();
    const results = setup();
    await user.click(screen.getByText("trigger"));
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    await user.click(screen.getByText("Confirm"));
    expect(results).toEqual([true]);
  });

  it("resolves false when the cancel button is clicked", async () => {
    const user = userEvent.setup();
    const results = setup();
    await user.click(screen.getByText("trigger"));
    await user.click(screen.getByText("Cancel"));
    expect(results).toEqual([false]);
  });

  it("resolves false on Escape", async () => {
    const user = userEvent.setup();
    const results = setup();
    await user.click(screen.getByText("trigger"));
    await user.keyboard("{Escape}");
    expect(results).toEqual([false]);
  });

  it("closes the dialog after a decision", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByText("trigger"));
    await user.click(screen.getByText("Confirm"));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });
});
