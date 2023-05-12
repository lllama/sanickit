# Routing

Sanic-kit copies SvelteKit’s is _filesystem-based router_. The paths of your codebase define the routes of your app:

*   `src/routes` is the root route
*   `src/routes/about` creates an `/about`route
*   `src/routes/blog/[slug]` creates a route with a _parameter_, `slug`, that can be used to load data dynamically when a user requests a page like `/blog/hello-world`

> You can change `src/routes` to a different directory by editing the [project config](https://kit.svelte.dev/configuration).

Each route directory contains one or more _route files_, which can be identified by their `+`prefix.

## +page.sanic

The `+page.sanic` file defines a page of your app. The file is a jinja template that will be included in your app’s layout. 

src/routes/+page.sanic

```html
<h1>Hello and welcome to my site!</h1>
<a href="/about">About my site</a>
```

src/routes/about/+page.sanic

```html
<h1>About this site</h1>
<p>TODO...</p>
<a href="/">Home</a>
```

src/routes/blog/\[slug\]/+page.sanic

Sometimes you will need to load some data to include in your template. Here the path contains the `[slug]` component which will be passed into your handler code. The handler code itself is included in a `<handler>` tag as shown below:

```html
<handler>
import some_orm
entry = some_orm.get(slug)
</handler>
    
<h1>{{entry.title}}</h1>
<div>{{entry.content}}</div>
```

Any variables defined in your handler code will be passed to your template as part of the context. Here we defined the `entry` variable which we use to get at the blog entry’s `title` and `content` attributes. 

## +server.py 

The +page.sanic file handles any GET requests made to the server. To handle other HTTP methods, create a server.py file and add functions named after the method you want to handle. E.g.

```python
async def POST(request):
   ...
```

The above code will then handle any POST requests sent to the application. 

## +layout

So far, we've treated pages as entirely standalone components — upon navigation, the existing `+page.svelte` component will be destroyed, and a new one will take its place.

But in many apps, there are elements that should be visible on _every_ page, such as top-level navigation or a footer. Instead of repeating them in every `+page.svelte`, we can put them in _layouts_.

### +layout.html

To create a layout that applies to every page, make a file called `src/routes/+layout.html`. The default layout that Sanic-Kit uses is:


...but we can add whatever markup, styles and behaviour we want. The only requirement is that the component includes a `<slot>` for the page content. For example, let's add a nav bar:

src/routes/+layout.sanic 

    <nav>
        <a href="/">Home</a>
        <a href="/about">About</a>
        <a href="/settings">Settings</a>
    </nav>
    
    <slot></slot>

If we create pages for `/`, `/about` and `/settings`...

src/routes/+page.svelte

    <h1>Home</h1>

src/routes/about/+page.svelte

    <h1>About</h1>

src/routes/settings/+page.svelte

    <h1>Settings</h1>

...the nav will always be visible, and clicking between the three pages will only result in the `<h1>` being replaced.

Layouts can be _nested_. Suppose we don't just have a single `/settings` page, but instead have nested pages like `/settings/profile`and `/settings/notifications` with a shared submenu (for a real-life example, see [github.com/settings](https://github.com/settings)).

We can create a layout that only applies to pages below `/settings` (while inheriting the root layout with the top-level nav):

src/routes/settings/+layout.svelte

    <script>
        /** @type {import('./$types').LayoutData} */    export let data;
    </script>
    
    <h1>Settings</h1>
    
    <div class="submenu">
        {#each data.sections as section}
            <a href="/settings/{section.slug}">{section.title}</a>
        {/each}
    </div>
    
    <slot></slot>

By default, each layout inherits the layout above it. Sometimes that isn't what you want - in this case, [advanced layouts](https://kit.svelte.dev/advanced-routing#advanced-layouts) can help you.

### Content negotiation

`+server.js` files can be placed in the same directory as `+page` files, allowing the same route to be either a page or an API endpoint. To determine which, SvelteKit applies the following rules:

*   `PUT`/`PATCH`/`DELETE`/`OPTIONS` requests are always handled by `+server.js` since they do not apply to pages
*   `GET`/`POST` requests are treated as page requests if the `accept` header prioritises `text/html` (in other words, it's a browser page request), else they are handled by `+server.js`

Other files[permalink](https://kit.svelte.dev/#other-files)
-----------------------------------------------------------

Any other files inside a route directory are ignored by SvelteKit. This means you can colocate components and utility modules with the routes that need them.

If components and modules are needed by multiple routes, it's a good idea to put them in [`$lib`](https://kit.svelte.dev/modules#$lib).