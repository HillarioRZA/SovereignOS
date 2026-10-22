'use client';
import { useState } from 'react';

export function useOfficeOasisState() {
  const [streamFilter, setStreamFilter] = useState<'All' | 'Execution' | 'Gates' | 'Lounge'>('All');
  return { streamFilter, setStreamFilter };
}
