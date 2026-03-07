"use client";

import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("Dashboard error:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center p-8">
          <div className="max-w-md rounded-lg border border-amber-200 bg-amber-50 p-8 text-center">
            <h2 className="mb-2 text-lg font-semibold text-amber-800">
              Something went wrong
            </h2>
            <p className="mb-4 text-sm text-amber-700">
              The dashboard encountered an error. Your data is safe.
            </p>
            <button
              onClick={() => {
                this.setState({ hasError: false });
                window.location.reload();
              }}
              className="rounded bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700"
            >
              Reload Dashboard
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
