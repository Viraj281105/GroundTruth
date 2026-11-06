import React from 'react';
import { StatusView } from '../../features/status/StatusView';

export const metadata = { title: 'System status' };

export default function Page() {
  return <StatusView />;
}
