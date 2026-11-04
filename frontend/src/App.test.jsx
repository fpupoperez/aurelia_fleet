import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";

vi.mock("./AskPage", () => ({ AskPage: () => <h1>Ask a technical question</h1> }));
vi.mock("./LibraryPage", () => ({ LibraryPage: () => <h1>Library</h1> }));
vi.mock("./AliasesPage", () => ({ AliasesPage: () => <h1>Aliases</h1> }));

test("navigation switches the page without a reload", async () => {
  window.history.pushState({}, "", "/");
  const user = userEvent.setup();
  render(<App />);
  expect(screen.getByRole("heading", { name: "Ask a technical question" })).toBeInTheDocument();
  await user.click(screen.getByRole("link", { name: "Library" }));
  expect(screen.getByRole("heading", { name: "Library" })).toBeInTheDocument();
  expect(window.location.pathname).toBe("/library");
  await user.click(screen.getByRole("link", { name: "Aliases" }));
  expect(screen.getByRole("heading", { name: "Aliases" })).toBeInTheDocument();
  await user.click(screen.getByRole("link", { name: "Aurelia" }));
  expect(screen.getByRole("heading", { name: "Ask a technical question" })).toBeInTheDocument();
});
