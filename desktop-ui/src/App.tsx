import { ConnectionBar } from "./components/ConnectionBar";
import { EventStream } from "./components/EventStream";
import { CommandInput } from "./components/CommandInput";

export default function App() {
  return (
    <div className="flex h-screen flex-col bg-void text-hud">
      <ConnectionBar />
      <EventStream />
      <CommandInput />
    </div>
  );
}
