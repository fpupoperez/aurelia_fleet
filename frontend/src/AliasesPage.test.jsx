import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AliasesPage } from "./AliasesPage";
import { createAlias, listAliases } from "./api";

vi.mock("./api", () => ({
  listAliases: vi.fn(),
  createAlias: vi.fn(),
  updateAlias: vi.fn(),
  deleteAlias: vi.fn(),
}));

test("a new group is saved from the comma-separated words", async () => {
  listAliases
    .mockResolvedValueOnce({ body: { data: { objects: [] } } })
    .mockResolvedValueOnce({
      body: { data: { objects: [{ aliasId: "a1", terms: ["gnss", "gps"] }] } },
    });
  createAlias.mockResolvedValue({ body: { success: true } });
  const user = userEvent.setup();
  render(<AliasesPage />);
  expect(await screen.findByText("No alias groups yet.")).toBeInTheDocument();
  await user.type(screen.getByLabelText("Words, separated by commas"), "gnss, gps");
  await user.click(screen.getByRole("button", { name: "Add alias" }));
  expect(createAlias).toHaveBeenCalledWith(["gnss", "gps"]);
  expect(await screen.findByDisplayValue("gnss, gps")).toBeInTheDocument();
});

test("a failed load shows the error", async () => {
  listAliases.mockRejectedValue(new Error("Aliases are unavailable."));
  render(<AliasesPage />);
  expect(await screen.findByText("Aliases are unavailable.")).toBeInTheDocument();
});
