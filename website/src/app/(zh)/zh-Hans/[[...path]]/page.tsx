import Page, {
  generateMetadata as metadataForPage,
} from "@/components/route-page";
import { pages } from "@/lib/content";
export const dynamicParams = false;
export function generateStaticParams() {
  return pages
    .filter((page) => page.locale === "zh-Hans")
    .map((page) => ({ path: page.canonicalPath.split("/").filter(Boolean) }));
}
type Props = { params: Promise<{ path?: string[] }> };
async function routeParams(params: Props["params"]) {
  return { path: [...["zh-Hans"], ...((await params).path ?? [])] };
}
export async function generateMetadata({ params }: Props) {
  return metadataForPage({ params: routeParams(params) });
}
export default function Route({ params }: Props) {
  return <Page params={routeParams(params)} />;
}
