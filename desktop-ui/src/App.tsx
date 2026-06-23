import { ConnectionBar } from "./components/ConnectionBar";
import { EventStream } from "./components/EventStream";
import { CommandInput } from "./components/CommandInput";
import { StatusPanel } from "./components/StatusPanel";
import { KillSwitch } from "./components/KillSwitch";
import { WireInspector } from "./components/WireInspector";

export default function App() {
  return (
    <div className="flex h-screen flex-col bg-void text-hud">
      <ConnectionBar />
      <div className="flex min-h-0 flex-1">
        <div className="flex min-h-0 flex-1 flex-col">
          <EventStream />
          <CommandInput />
        </div>
        <StatusPanel />
      </div>
      <WireInspector />
      <div className="flex items-center justify-end border-t border-hud-dim/30 bg-panel/80 px-4 py-2">
        <KillSwitch />
      </div>
    </div>
  );
}
