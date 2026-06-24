import { ConnectionBar } from "./components/ConnectionBar";
import { AlfredCore } from "./components/AlfredCore";
import { EventStream } from "./components/EventStream";
import { CommandInput } from "./components/CommandInput";
import { StatusPanel } from "./components/StatusPanel";
import { MemoryPanel } from "./components/MemoryPanel";
import { KillSwitch } from "./components/KillSwitch";
import { WireInspector } from "./components/WireInspector";

export default function App() {
  return (
    <div className="hud-grid relative flex h-screen flex-col overflow-hidden bg-void text-hud">
      <div className="hud-scanlines hud-vignette pointer-events-none absolute inset-0 z-10" />
      <div className="relative z-0 flex h-full flex-col">
        <ConnectionBar />
        <div className="flex min-h-0 flex-1">
          <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            <AlfredCore />
            <EventStream />
            <CommandInput />
          </div>
          {/* AlfredCore is flex-1 and vertically centers the reactor; the event
              log sits as a bounded strip beneath it (see EventStream max-height). */}
          <div className="flex w-80 min-h-0 flex-col">
            <StatusPanel />
            <MemoryPanel />
          </div>
        </div>
        <WireInspector />
        <div className="flex items-center justify-end border-t border-hud-dim/30 bg-panel/80 px-4 py-2">
          <KillSwitch />
        </div>
      </div>
    </div>
  );
}
