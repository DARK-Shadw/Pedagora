/**
 * Classroom v2 layout — full viewport, no sidebar, no topbar.
 * Google Meet style: the classroom IS the entire screen.
 */
export default function ClassroomV2Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 bg-[#0d1117] overflow-hidden">
      {children}
    </div>
  );
}
