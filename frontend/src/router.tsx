import { createRootRoute, createRoute, createRouter } from "@tanstack/react-router";

import { ActivityPage } from "./routes/activity";
import { CreatePage } from "./routes/create";
import { HomePage } from "./routes/home";
import { HowItWorksPage } from "./routes/how-it-works";
import { MarketDetailPage } from "./routes/market-detail";
import { MarketsPage } from "./routes/markets";
import { PortfolioPage } from "./routes/portfolio";
import { NotFound, RootLayout } from "./routes/root";

const rootRoute = createRootRoute({
  component: RootLayout,
  notFoundComponent: NotFound,
});

const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: HomePage });

const marketsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/markets",
  component: MarketsPage,
});

const marketDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/markets/$id",
  component: MarketDetailPage,
});

const createRouteDef = createRoute({
  getParentRoute: () => rootRoute,
  path: "/create",
  component: CreatePage,
});

const portfolioRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/portfolio",
  component: PortfolioPage,
});

const activityRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/activity",
  component: ActivityPage,
});

const howItWorksRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/how-it-works",
  component: HowItWorksPage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  marketsRoute,
  marketDetailRoute,
  createRouteDef,
  portfolioRoute,
  activityRoute,
  howItWorksRoute,
]);

export const router = createRouter({ routeTree, defaultPreload: "intent" });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
