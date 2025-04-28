This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Navigation Bar: Active Tab Highlighting & Accessibility

The bottom navigation bar provides quick access to all major app sections (Inbox/Tasks, Training, History, Settings). It is designed mobile-first and is always visible at the bottom of the screen.

### Active Tab Highlighting
- The navigation bar automatically highlights the active tab based on the current route.
- Only one tab is highlighted at any time, using a distinct color, background, and font weight for clarity.
- The highlight updates instantly as you navigate between sections—no manual refresh required.

### Accessibility
- The active tab includes `aria-current="page"` for screen reader support.
- All navigation items are keyboard accessible (tab/enter/space) and have a minimum touch target of 44x44px for mobile usability.
- Focus styles are visible for keyboard users, and color contrast meets accessibility guidelines.

You can find the implementation in `src/components/BottomNav.tsx`.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
