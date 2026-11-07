import React from 'react';
import { NewCaseForm } from '../../../features/cases/NewCaseForm';

export const metadata = {
  title: 'Ingest Real Project · GroundTruth',
  description: 'Register and calibrate a new real-world carbon or restoration project for independent causal screening.',
};

export default function NewCasePage() {
  return <NewCaseForm />;
}

