'use client';

import React from 'react';
import { RouteError } from '../../../../../../components/shell/RouteStates';

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError error={error} reset={reset} what="this project" />;
}
