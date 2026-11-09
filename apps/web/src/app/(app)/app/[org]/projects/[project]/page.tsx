import { redirect } from 'next/navigation';

export const dynamic = 'force-dynamic';

export default function ProjectIndex({ params }: { params: { org: string; project: string } }) {
  redirect(`/app/${params.org}/projects/${params.project}/overview`);
}
