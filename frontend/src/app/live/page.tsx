import { IntelDashboard } from "@/components/intel-dashboard";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function LivePage() {
  return <IntelDashboard />;
}
