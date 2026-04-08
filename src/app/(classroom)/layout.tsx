/**
 * Classroom route group layout — completely independent from the app layout.
 * No sidebar, no topbar, no footer. Full viewport for the classroom.
 */
export default function ClassroomLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
