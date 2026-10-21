import { ChannelOverview } from '@/widgets/channel-overview';
import { SystemStatus } from '@/widgets/system-status';

export function DashboardPage() {
  return (
    <>
      <ChannelOverview status={<SystemStatus />} />
    </>
  );
}
