/**
 * Polyfills for older browsers
 * Import this first in your app entry point
 */

// Promise.withResolvers polyfill (for older browsers)
if (typeof Promise.withResolvers === "undefined") {
  (Promise as any).withResolvers = function <T>(): {
    promise: Promise<T>;
    resolve: (value: T | PromiseLike<T>) => void;
    reject: (reason?: any) => void;
  } {
    let resolve!: (value: T | PromiseLike<T>) => void;
    let reject!: (reason?: any) => void;
    const promise = new Promise<T>((res, rej) => {
      resolve = res;
      reject = rej;
    });
    return { promise, resolve, reject };
  };
}

// Array.at polyfill
if (!Array.prototype.at) {
  Array.prototype.at = function (index: number) {
    if (index < 0) {
      index = this.length + index;
    }
    return this[index];
  };
}

// String.replaceAll polyfill
if (!String.prototype.replaceAll) {
  String.prototype.replaceAll = function (search: string | RegExp, replace: string) {
    if (typeof search === "string") {
      return this.split(search).join(replace);
    }
    return this.replace(search, replace);
  };
}

export {};
