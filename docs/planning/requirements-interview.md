# Personal Blog Requirements Interview

Status: in progress
Protocol: Ask one coherent subject per round. A subject may contain all closely related decision questions. Record the user answer and resulting decisions before moving to the next subject. This document is the source for the implementation plan.

## Established Context

- Development server: blog.
- Code root: /home/code/.
- Intended project directory: /home/code/personal-blog/.
- Preferred stack under consideration: Python, Django, PostgreSQL, Docker Compose, and Caddy.
- The final stack and product scope remain subject to this interview.

## Interview


### Q001 - Content Visibility


Question: What are the intended visibility rules for articles and other blog content?

Answer: Blog content has three visibility levels: public, authenticated, and private.

Decision: Use public, authenticated, and private as the initial content visibility model.
Notes: Draft, scheduled, archived, and moderation states will be modeled separately from visibility.

### Q002 - Private Content Audience and Authoring

Question: Who may view private content, and which accounts may create posts?

Answer: Private content is visible only to its author. The current project has one account that is both administrator and author. Other registered users cannot publish posts and have only limited interaction permissions such as commenting.

Decision: Model a single administrator-author account. Private articles are author-only. Ordinary users have no authoring capability.

Notes: The account creation and activation policy for ordinary users remains undecided.

### Q003 - Registration and Activation

Question: How do ordinary users create and activate accounts?

Answer: The administrator can open or close direct registration. The administrator can also issue invitation codes for registration. No manual approval is required.

Decision: Support administrator-controlled direct registration and invitation-code registration. Accounts do not require manual review.

Notes: Invitation-code usage limits, expiration, and revocation behavior remain undecided.

### Q004 - Invitation Code Usage Limit

Question: How many accounts may each invitation code register?

Answer: Each invitation code may register only one account.

Decision: Invitation codes are single-use and become unusable after a successful registration.

Notes: The expiration rule for unused codes remains undecided.

### Q005 - Invitation Code Expiration

Question: How long should unused invitation codes remain valid?

Answer: Use four expiration tiers: 1, 3, 7, or 30 days.

Decision: The administrator selects a 1-day, 3-day, 7-day, or 30-day validity period when generating each invitation code. Unused codes expire automatically at the selected deadline.

Notes: The administrator should also be able to revoke an unused code; this will be specified later.

### Q006 - Comment Visibility and Participation

Question: Which users may view and publish comments?

Answer: Unauthenticated visitors may view some unlocked articles and their comments. Ordinary users may view all articles and comments. For each article, its author may require login to view comments and may separately require login to publish comments.

Decision: Support per-article settings for comment-view login requirement and comment-post login requirement. Publicly visible unlocked content and comments may be viewed by unauthenticated visitors.

Open point: The statement that ordinary users may view all articles conflicts with the earlier author-only rule for private articles and must be resolved before finalizing access control.

### Q007 - Private Article Boundary

Question: Does ordinary-user access to all articles include private articles?

Answer: No. Private articles are personal journal records and must not be public.

Decision: Ordinary users may access public and authenticated articles only. Private articles remain author-only personal records.

Notes: This resolves the access-control conflict recorded in Q006.

### Q008 - Anonymous Comment Publishing

Question: When an article does not require login to comment, may unauthenticated visitors publish comments?

Answer: Yes. The comment-login requirement is configured separately for each article during article creation and editing.

Decision: Allow anonymous comments when the article-level comment-login requirement is disabled. Expose this setting in both article creation and article editing.

Notes: Required anonymous-comment identity fields and moderation behavior remain undecided.

### Q009 - Anonymous Comment Buffer and Removal

Question: What identity information is required for anonymous comments, and how are they published?

Answer: Anonymous commenters provide no identity information. A submitted comment is buffered for 10 minutes before it is publicly displayed, allowing the article author time to block unsuitable content. The author may delete a comment during or after that buffer period.

Decision: Anonymous comments require no identity fields. Hold each submitted anonymous comment from public display for 10 minutes, then publish it automatically unless the article author deletes it. The author may delete comments at any time.

Notes: Whether the same 10-minute buffer applies to comments from authenticated users remains undecided.

### Q010 - Authenticated Comment Buffer

Question: Do comments from authenticated users also require the 10-minute public-display buffer?

Answer: Yes.

Decision: Apply the same 10-minute automatic public-display buffer to every comment, whether anonymous or authenticated.

Notes: Comment reply structure remains undecided.

### Q011 - Comment Replies

Question: Should commenters be able to reply to a specific comment?

Answer: Yes.

Decision: Support threaded replies to individual comments.

Notes: The maximum reply nesting depth remains undecided.

### Q012 - Reply Depth and Comment Closure

Question: What is the maximum nesting depth for comment replies?

Answer: There is no reply-depth limit. When a thread exceeds 100 levels, notify the article author. The author can also configure whether each article accepts new comments; closing comments prevents future comments but does not hide existing comments.

Decision: Allow unbounded reply nesting and alert the author once a comment thread exceeds 100 levels. Add an article-level comments-enabled setting that blocks new comments while retaining the visibility of existing comments.

Notes: The default value for comments-enabled on newly created articles remains undecided.

### Q013 - Default Comment Setting

Question: Should newly created articles allow new comments by default?

Answer: Yes.

Decision: Set comments-enabled to true by default for new articles; the author may change it during creation or editing.

Notes: Anonymous-comment display identity remains undecided.

### Q014 - Anonymous Comment Display Name

Question: What author name should an anonymous comment display?

Answer: 访客.
Decision: Display every anonymous comment author as 访客.
Notes: The display-name rule for authenticated users remains undecided.

### Q015 - Authenticated Comment Display Name

Question: What name should an authenticated user comment display?

Answer: Display a user-configured nickname; if no nickname is set, display the account name.

Decision: Store an optional nickname for each ordinary user and use account name as the display fallback.

Notes: The login identifier and account-name format remain undecided.

### Q016 - Registration Identifier and Email Verification

Question: Should registration and login use a username, an email address, or both?

Answer: Use an email address. Registration requires a verification code sent to that email address.

Decision: Use email address as the account identifier and require email-verification-code confirmation before creating an account.

Notes: The regular login credential and email-code lifetime remain undecided.

### Q017 - Login Methods

Question: What regular login methods should users have?

Answer: Users may choose either email plus password or an email verification code.

Decision: Support password login and passwordless email-code login as alternative sign-in methods.

Notes: Password policy and email-login-code security rules remain undecided.

### Q018 - Password Strength Baseline

Question: What minimum password strength should be required?

Answer: At least 8 characters and at least two character categories among numbers and English characters.

Decision: Require passwords of at least 8 characters with at least two character categories.

Notes: The exact category definitions, including uppercase, lowercase, digits, and symbols, remain undecided.

### Q019 - Password Character Categories

Question: Are uppercase letters, lowercase letters, digits, and symbols separate password character categories?

Answer: Yes, each is a separate category.

Decision: Evaluate uppercase English letters, lowercase English letters, digits, and symbols as four distinct password categories; a valid password must use at least two.

Notes: Password reset and login-attempt limits remain undecided.

### Q020 - Email Verification Code Lifetime

Question: How long should email verification codes remain valid for registration, password login, and passwordless login?

Answer: 10 minutes.

Decision: Every email verification code expires 10 minutes after issuance.

Notes: Verification-attempt limit and resend-rate limit remain undecided.

### Q021 - Verification Code Attempt Limit

Question: After how many incorrect verification-code attempts should the current code become invalid?

Answer: After 5 incorrect attempts, invalidate the current code and require a newly sent code.

Decision: Invalidate a verification code after its fifth failed verification attempt. A new send action is required before another attempt.

Notes: Verification-code resend interval remains undecided.

### Q022 - Verification Code Resend

Question: What minimum interval is required before the same email address may request another verification code?

Answer: 1 minute. Generating a later code invalidates the earlier code.

Decision: Enforce a 1-minute resend interval per email address. Issuing a new code immediately invalidates any earlier active code for that email and purpose.

Notes: Verification-code format and length remain undecided.

### Q023 - Verification Code Format

Question: What format should email verification codes use?

Answer: 6 digits.

Decision: Generate six-digit numeric email verification codes.

Notes: Password-reset flow remains undecided.

### Q024 - Password Reset

Question: Should a user reset a forgotten password by verifying a code sent to the verified email address?

Answer: Yes.

Decision: Implement password reset through a verification code sent to the users verified email address.

Notes: The impact of a password reset on existing login sessions remains undecided.

### Q025 - Session Revocation After Password Reset

Question: After a password reset, should all existing sessions on other devices be immediately signed out?

Answer: Yes.

Decision: Revoke every active session for the account immediately after a successful password reset.

Notes: Normal session lifetime remains undecided.

### Q026 - Remembered Login Session

Question: How long should a normal login session remain valid?

Answer: When the user selects 30-day remembered login, the same device and browser remain signed in for 30 days.

Decision: Offer a 30-day remembered-login option scoped to the same browser on the same device.

Notes: The default session behavior when remembered login is not selected remains undecided.

### Q027 - Default Login Session

Question: When the user does not select 30-day remembered login, should closing the browser immediately end the session?

Answer: Keep the session for 12 hours.

Decision: Issue a default login session that expires after 12 hours, independent of browser closure.

Notes: Email-address change rules remain undecided.

### Q028 - Email Address Change Verification

Question: Must a user verify a new email address before changing the account email?

Answer: Yes.

Decision: Require successful verification of the new email address before applying an account-email change.

Notes: Re-authentication requirements for initiating an email-address change remain undecided.

### Q029 - Email Change Re-authentication

Question: Must a logged-in user re-enter the current password or verify through the current email before changing the email address?

Answer: No. An active login session plus verification of the new email address is sufficient.

Decision: Permit an authenticated user to change the account email after verifying the new email, without additional current-password or old-email verification.

Notes: Active-session behavior after an email-address change remains undecided.

### Q030 - Password Change Authentication

Question: Must an authenticated user enter the current password before voluntarily changing it?

Answer: Yes.

Decision: Require the current password before a logged-in user may set a new password.

Notes: Existing-session revocation after a voluntary password change remains undecided.

### Q031 - Password Change Session Revocation

Question: After a voluntary password change, should active sessions on other devices be immediately signed out?

Answer: Yes. Because the user is already authenticated, no email verification code is required for this password change.

Decision: A logged-in password change requires the current password but no email code, and revokes sessions on other devices after success.

Notes: Whether the initiating session remains active remains undecided.

### Q032 - Initiating Session After Password Change

Question: After a voluntary password change, should the current device and browser remain signed in?

Answer: Keep it signed in and update the credential representing that retained session.

Decision: Preserve the initiating session after password change, but rotate its session credential. Other-device sessions remain revoked.

Notes: User account-deletion capability remains undecided.

### Q033 - User Self-Service Account Deletion

Question: May ordinary users delete their own accounts?

Answer: No.

Decision: Do not provide self-service account deletion for ordinary users.

Notes: Administrator account-disable and deletion capabilities remain undecided.

### Q034 - Administrator Account Disablement

Question: May the administrator disable a normal users ability to sign in?

Answer: Yes.

Decision: Give the administrator the ability to disable an ordinary user account and block future sign-in.

Notes: The visibility of comments already published by a disabled user remains undecided.

### Q035 - Comments After Account Disablement

Question: After an ordinary user is disabled, should that users already-public comments remain visible or be hidden?

Answer: They remain visible and are unaffected.

Decision: Account disablement blocks future login only; previously public comments remain displayed.

Notes: Article authoring format remains undecided.

### Q036 - Article Authoring Formats

Question: Should the article editor support rich text, Markdown, or both?

Answer: Both.

Decision: Provide both rich-text and Markdown authoring capabilities in the administration interface.

Notes: Per-article format selection and canonical storage format remain undecided.

### Q037 - Per-Article Content Format

Question: May a single article mix rich text and Markdown, or switch formats later?

Answer: Do not mix formats. The author selects one format, and the choice cannot be changed later.

Decision: Require exactly one immutable content format per article, chosen during article creation.

Notes: Cover-image requirements remain undecided.

### Q038 - Article Cover Image

Question: Does every article need a cover image?

Answer: Yes. Use an uploaded cover image when the author provides one; otherwise use a default image.

Decision: Render every article with a cover image, prioritizing an author upload and falling back to a default cover asset.

Notes: Default-cover selection and upload constraints remain undecided.

### Q039 - Default Cover Selection

Question: When no cover is uploaded, should the author choose from a preset gallery or should one site-wide default be used?

Answer: Use one site-wide default.

Decision: Use a single global default cover image for every article without an uploaded cover.

Notes: Allowed cover-upload formats and size remain undecided.

### Q040 - Cover Upload Formats

Question: Which image formats may be uploaded as an article cover?

Answer: PNG, JPG, GIF, and WebP.

Decision: Accept PNG, JPEG/JPG, GIF, and WebP cover uploads.

Notes: Maximum cover-upload file size remains undecided.

### Q041 - Cover Upload Size

Question: What maximum file size and resolution constraints apply to an article cover upload?

Answer: Resolution is unrestricted. File size must not exceed 5 MB.

Decision: Accept cover images at any resolution, with a strict maximum upload size of 5 MB per file.

Notes: Inline article-image support remains undecided.

### Q042 - Inline Article Images and Storage

Question: May article bodies upload and insert images?

Answer: Yes. Uploaded images are stored on the server in a user-specific folder, with separate subfolders for each article.

Decision: Support inline-image upload and insertion. Store media under an author-specific server directory, partitioned again by article.

Notes: Inline-image formats and size limits remain undecided.

### Q043 - Inline Image Formats

Question: Which formats may be uploaded as inline article images?

Answer: The same formats as article covers.

Decision: Accept PNG, JPEG/JPG, GIF, and WebP inline-image uploads.

Notes: Inline-image file-size limit remains undecided.

### Q044 - Inline Image Size

Question: What maximum file size applies to a single inline article image?

Answer: 5 MB.

Decision: Enforce a 5 MB maximum upload size per inline article image.

Notes: Lifecycle rules for unreferenced article images remain undecided.

### Q045 - Unreferenced Inline Image Cleanup

Question: After article editing, should an uploaded image no longer referenced by the body be deleted immediately or retained for future reuse?

Answer: Delete it.

Decision: Immediately remove an inline image from server storage when it is no longer referenced by its article body.

Notes: Media cleanup when an entire article is deleted remains undecided.

### Q046 - Article Deletion Cooling Period

Question: When an entire article is deleted, should its cover and inline images also be removed from the server?

Answer: Use a 7-day cooling period, then delete.

Decision: Soft-delete an article and retain its cover and inline media for 7 days. Permanently delete the article and associated media after the cooling period.

Notes: Article restoration during the 7-day cooling period remains undecided.

### Q047 - Article Restoration

Question: May the author restore a deleted article during its 7-day cooling period?

Answer: Yes.

Decision: Allow the author to restore a soft-deleted article and its retained media before the 7-day deadline.

Notes: Article publication states remain undecided.

### Q048 - Article Publication States

Question: Besides published, should articles support draft and scheduled-publication states?

Answer: Yes.

Decision: Support draft, published, and scheduled publication states for articles.

Notes: Scheduling timezone remains undecided.

### Q049 - Scheduled Publication Timezone

Question: Which timezone should scheduled article publication use?

Answer: Shanghai.

Decision: Interpret and display scheduled publication times in Asia/Shanghai timezone.

Notes: Publication behavior for edits to an already published article remains undecided.

### Q050 - Published Article Edit Workflow

Question: After an already published article is edited, should changes be immediately visible or require publication again?

Answer: Require clicking publish again. The user may enable a profile preference that does not require clicking publish again.

Decision: Default to explicit republishing after edits to a published article. Provide an author profile preference that automatically publishes saved edits.

Notes: Reader visibility of the previous published version while a new edit awaits publication remains undecided.

### Q051 - Reader Visibility During Pending Republishing

Question: While the author edits a published article but has not republished it, should readers see the old version or lose access?

Answer: Readers see the old version.

Decision: Keep the previously published version visible to readers until the edited revision is explicitly or automatically republished.

Notes: Historical-version retention remains undecided.

### Q052 - Article Version History

Question: Should published article revisions be retained so the author can view and restore old versions?

Answer: Keep a version-history timeline that the author can inspect and attempt to restore from.

Decision: Retain article revision history and provide an author-facing timeline for viewing and restoring earlier versions.

Notes: Version-retention limit remains undecided.

### Q053 - Version Retention

Question: How long or how many historical versions should each article retain?

Answer: Retain every version for as long as the current article has not been deleted.

Decision: Keep the complete revision history without a time or count limit while its article remains active.

Notes: Article categorization remains undecided.

### Q054 - Article Tags

Question: Does the article need a categorization feature?

Answer: Articles may be assigned tags.

Decision: Support tags for organizing and filtering articles.

Notes: Whether a separate category taxonomy is also needed remains undecided.

### Q055 - Article Sections

Question: Is a separate article category taxonomy needed in addition to tags?

Answer: Articles may be published into sections, and a section is selected before publication.

Decision: Support article sections alongside tags. Require an article to select a section before it can be published.

Notes: Section-management authority and hierarchy remain undecided.

### Q056 - Section Management Authority

Question: Who may create, edit, and delete article sections?

Answer: The administrator.

Decision: Restrict section lifecycle management to the administrator.

Notes: Whether an article may belong to more than one section remains undecided.

### Q057 - Article Section Cardinality

Question: May one article belong to multiple sections?

Answer: No.

Decision: Assign each article to exactly one section before publication.

Notes: Per-article tag limit remains undecided.

### Q058 - Tag Limit and Search

Question: How many tags may a single article have?

Answer: At most 10 tags. Search supports site-wide tag search.

Decision: Limit each article to 10 tags and provide a site-wide tag-search capability.

Notes: Tag creation and lifecycle authority remain undecided.

### Q059 - Tag Creation and Approval

Question: May an author create a new tag while editing an article?

Answer: Authors and administrators may create tags. Tags created by authors become site-wide tags only after administrator approval.

Decision: Allow author-proposed tags and administrator-created tags. Place author-proposed tags in pending review; approval promotes them to site-wide tags.

Notes: Visibility and usability of a pending author-proposed tag before approval remain undecided.

### Q060 - Pending Tag Visibility and Rejection

Question: May an author-proposed tag appear on that authors article before approval?

Answer: Yes. If the tag is rejected, remove it from the articles tags.

Decision: Display and apply pending author-proposed tags immediately on the relevant article. If rejected, automatically remove the tag from every article using that pending tag.

Notes: Author notification of tag-approval outcomes remains undecided.

### Q061 - Review Notifications

Question: Should the author be notified when an administrator approves or rejects an author-proposed tag?

Answer: Yes, through an in-site notification system. All review outcomes may be communicated through this notification system.

Decision: Implement an in-site notification system as the canonical delivery channel for tag-review and other review outcomes.

Notes: Whether review notifications are also delivered by email remains undecided.

### Q062 - Email Notification Scope

Question: Should in-site review notifications also be sent to the users email address?

Answer: No. Email notifications are a more advanced feature and are out of scope for now, except for verification codes.

Decision: Deliver only verification codes by email in the initial release. Keep review and other non-verification notifications in-site only.

Notes: In-site notification read-state and retention rules remain undecided.

### Q063 - Notification Read State and Broadcast Tracking

Question: Should in-site notifications distinguish unread and read states?

Answer: Yes. For administrator-sent group notifications, the notification-management interface shows which recipients have read or not read it.

Decision: Track read state per notification recipient. Provide administrator broadcast-notification management with recipient-level read/unread visibility.

Notes: Broadcast audience-selection rules remain undecided.

### Q064 - Broadcast Audience Selection

Question: Which recipient scopes may an administrator select when sending a broadcast notification?

Answer: The administrator may not select recipient scopes.

Decision: Do not provide manual recipient-scope selection for administrator broadcast notifications.

Notes: The fixed default recipient population for a broadcast remains undecided.

### Q065 - Broadcast Default Audience

Question: When recipient scopes cannot be selected, who receives every administrator broadcast notification by default?

Answer: All registered users.

Decision: Deliver every administrator broadcast notification to all registered users.

Notes: Notification retention period remains undecided.

### Q066 - Notification Retention and Visibility

Question: How long should in-site notifications be retained?

Answer: They persist until the administrator deletes them. Users cannot delete notifications. Reading removes the red-dot or unread-count indicator. If the administrator deletes or hides a notification, no user can see it.

Decision: Retain notifications indefinitely unless the administrator deletes or hides them. Users cannot remove notifications. Marking a notification read clears its unread badge. Administrator deletion and hiding remove it from every user view.

Notes: Whether an administrator may restore a hidden notification remains undecided.

### Q067 - Hidden Notification Restoration

Question: May an administrator later restore a hidden notification to user visibility?

Answer: Yes.

Decision: Treat hiding as reversible: the administrator may restore a hidden notification for users later.

Notes: Event types that create in-site notifications remain undecided.

### Q068 - Additional Notification Events

Question: Besides tag-review outcomes and administrator broadcasts, which events should create an in-site notification?

Answer: None for now.

Decision: In the initial release, generate in-site notifications only for tag-review outcomes and administrator broadcasts.

Notes: Article-like interaction remains undecided.

### Q069 - Article Likes

Question: Does an article need a like feature?

Answer: No.

Decision: Do not implement article likes.

Notes: Article bookmarking remains undecided.

### Q070 - Article Bookmarks and View Count

Question: Do logged-in users need to bookmark articles for later reading?

Answer: Yes. Articles also display their view count.

Decision: Provide logged-in article bookmarking and display an article view count.

Notes: View-count deduplication and counting window remain undecided.

### Q071 - View Count Frequency

Question: When the same visitor or logged-in user repeatedly views an article, when should another view be counted?

Answer: Every time they click to enter it again.

Decision: Increment the article view count on every new article-entry action, without visitor or user deduplication window.

Notes: Whether the article authors own views are counted remains undecided.

### Q072 - Author Views

Question: Do views by the article author count toward the displayed view count?

Answer: Yes. Any person who visits the article interface adds one view.

Decision: Count every article-page visit as one view regardless of visitor identity, including the article author.

Notes: Bookmark-list visibility remains undecided.

### Q073 - Bookmark Privacy

Question: Is a users bookmarked-article list visible only to that user?

Answer: Yes.

Decision: Keep each users bookmark list private to that user.

Notes: Bookmark behavior after a target article becomes unavailable remains undecided.

### Q074 - Lost Bookmarked Articles

Question: What should happen to a bookmark when its target article becomes private, deleted, or otherwise inaccessible?

Answer: Keep it in the list with the text 该文章已丢失 and its cover image. The user may remove the bookmark themselves.

Decision: Preserve inaccessible bookmarks as private lost-article entries, showing a lost-article description and cover image. Do not automatically remove them; let the user delete them.

Open point: Article deletion removes associated media after 7 days, so the retained cover for a lost bookmark needs an explicit persistence rule.

### Q075 - Lost Bookmark Cover Asset

Question: After permanent article deletion, should a special thumbnail be retained solely for lost bookmarks?

Answer: Use one dedicated lost-bookmark image for every lost bookmark.

Decision: Do not retain deleted article covers for bookmarks. Render every lost bookmark with a single site-wide lost-bookmark asset, allowing original article media to be fully deleted.

Notes: Full-text article search remains undecided.

### Q076 - Article Search Scope

Question: Besides site-wide tag search, should search cover article titles and body content?

Answer: Search titles only; do not search body content.

Decision: Implement article-title search and exclude article body content from search indexing. Search results must enforce the existing content-visibility rules.

Notes: Title-search matching behavior remains undecided.

### Q077 - Title Search Matching

Question: Should title search support fuzzy matching?

Answer: Yes.

Decision: Support fuzzy matching for article-title search.

Notes: Default search-result ordering remains undecided.

### Q078 - Title Search Result Ordering

Question: Should title-search results default to relevance or publication time ordering?

Answer: Relevance is the primary ordering and time is secondary.

Decision: Sort title-search results first by relevance score, then by publication time for ties.

Notes: Default home-page article-list ordering remains undecided.

### Q079 - Home Article Ordering

Question: How should the blog home page order its article list by default?

Answer: By actual publication time, with the newest published article first.

Decision: Order the home-page article list by publication timestamp descending.

Notes: Home-page page size remains undecided.

### Q080 - Home Article Page Size

Question: How many articles should the home page show per page by default?

Answer: Show 20 by default, with bottom controls for 10, 20, or 50.

Decision: Default to 20 articles per page and let the reader choose 10, 20, or 50 from controls at the bottom of the list.

Notes: Cross-page navigation style remains undecided.

### Q081 - Article List Navigation

Question: Should article-list navigation use numbered pagination or infinite scrolling?

Answer: Numbered pagination.

Decision: Use traditional numbered pagination for article lists.

Notes: Home-page section and tag filtering remain undecided.

### Q082 - Home Filtering and Section Navigation

Question: Should the home page provide filtering by article sections and tags?

Answer: The home page directly shows all articles and has tag filtering. The navigation bar can enter each section to view its articles.

Decision: Keep the home page as an all-article list with tag filtering. Provide navigation-bar entry points for dedicated section article lists.

Notes: Single-tag versus multi-tag filtering remains undecided.

### Q083 - Multi-Tag Home Filtering

Question: May users select multiple tags together when filtering the home page?

Answer: Yes, up to five tags.

Decision: Support combined home-page tag filtering with a maximum of five selected tags.

Notes: Multi-tag matching logic remains undecided.

### Q084 - Multi-Tag Match Logic

Question: For multiple selected tags, must an article contain all tags or may it contain any selected tag?

Answer: Articles containing any selected tag may be displayed, with the most matching tags first.

Decision: Use OR matching for selected tags. Sort matching articles by count of selected tags matched descending, then by publication time descending for ties.

Notes: Article table-of-contents behavior remains undecided.

### Q085 - Article Table of Contents

Question: Should long article pages automatically generate a table of contents from headings?

Answer: Yes.

Decision: Automatically generate a table of contents on article pages from article headings.

Notes: Included heading levels remain undecided.

### Q086 - Table of Contents Heading Level

Question: Which heading levels should the generated table of contents include?

Answer: Second-level headings.

Decision: Include only H2 headings in the automatically generated article table of contents.

Notes: Article sharing controls remain undecided.

### Q087 - Article Sharing

Question: Should article pages provide copy-link or external-platform sharing controls?

Answer: Yes. Sharing externally also just automatically copies the article link; do not directly integrate any platform for now.

Decision: Provide a share control that copies the article URL to the clipboard. Do not implement direct social-platform integrations in the initial release.

Notes: Theme and dark-mode requirements remain undecided.

### Q088 - Theme Color Modes

Question: Does the site need dark mode?

Answer: Support different color modes.

Decision: Implement selectable site color modes rather than a single fixed palette.

Notes: The initial set of color modes and default-selection behavior remain undecided.

### Q089 - Initial Color Modes

Question: Which specific color modes should the first release provide?

Answer: Light, dark, and eye-care.

Decision: Provide light, dark, and eye-care color modes in the initial release.

Notes: Default mode for a first-time visitor remains undecided.

### Q090 - Default Color Mode

Question: Which color mode should a first-time visitor see by default?

Answer: Light.

Decision: Default first-time visitors to the light color mode.

Notes: Persistence scope for a user-selected color mode remains undecided.

### Q091 - Color Preference Synchronization

Question: Should a selected color mode be stored only in the current browser or synchronized to the logged-in account?

Answer: Synchronize it to the account.

Decision: Persist each authenticated users selected color mode in the account and synchronize it across devices.

Notes: Color-mode selection for unauthenticated visitors remains undecided.

### Q092 - Anonymous Color Preference

Question: May unauthenticated visitors switch among light, dark, and eye-care modes?

Answer: Yes, and save the choice in the browser.

Decision: Allow unauthenticated visitors to select color modes and persist the selection in their current browser. Authenticated account preference remains the cross-device source of truth.

Notes: User avatar support remains undecided.

### Q093 - User Avatar Upload

Question: May users upload and set a personal avatar?

Answer: Yes. Use the same size and format requirements as article cover images.

Decision: Support avatar uploads in PNG, JPEG/JPG, GIF, and WebP formats, each at most 5 MB with unrestricted resolution.

Notes: Default avatar behavior remains undecided.

### Q094 - Default Avatar Content

Question: When a user has not uploaded an avatar, should the site show one shared default image or an account-generated avatar?

Answer: Generate one from the first character of the nickname or account.

Decision: Render a generated text avatar using the first nickname character, with the first account character as fallback, when no avatar image is uploaded.

Notes: Generated-avatar background-color rule remains undecided.

### Q095 - Generated Avatar Palette

Question: Should generated text avatars use one fixed background color or account-derived colors?

Answer: Use one unified palette, to be chosen by you.

Decision: Use a consistent generated-avatar color palette selected during the interface-design phase.

Notes: Avatar display shape remains undecided.

### Q096 - Avatar Shape

Question: Should avatars be circular, rounded square, or another shape?

Answer: Circular.

Decision: Render uploaded and generated avatars as circles throughout the site.

Notes: Nickname length and validation remain undecided.

### Q097 - Nickname Validation

Question: What is the maximum length for a user nickname?

Answer: At most 8 Chinese characters or 16 English letters. Special characters and punctuation are forbidden.

Decision: Permit only Chinese characters and English letters in nicknames, with a maximum of 8 Chinese characters or 16 English letters.

Notes: Length calculation for mixed Chinese-and-English nicknames remains undecided.

### Q098 - Mixed Nickname Length

Question: How should nickname length be calculated when Chinese characters and English letters are mixed?

Answer: One Chinese character counts as two English letters.

Decision: Measure nickname length in a 16-unit budget: each Chinese character costs 2 units and each English letter costs 1 unit.

Notes: Nickname uniqueness remains undecided.

### Q099 - Nickname Uniqueness

Question: May different users use the same nickname?

Answer: No. Duplicates must be checked.

Decision: Enforce site-wide unique nicknames and validate uniqueness on nickname creation and change.

Notes: Nickname-change frequency remains undecided.

### Q100 - Nickname Change Cooldown

Question: How often may a user change their nickname?

Answer: A 7-day waiting period.

Decision: Enforce a 7-day cooldown after each successful nickname change.

Notes: Public user-profile pages remain undecided.

### Q101 - Public User Profile Content

Question: Should ordinary users have publicly accessible profile pages?

Answer: A public profile displays only the users published articles.

Decision: Public user profile pages show only that users published articles and no other profile data.

Notes: Visibility behavior for a user with no published articles remains undecided.

### Q102 - Empty Public Profiles

Question: Should a user profile remain accessible when that user has no published articles?

Answer: Yes, display it as empty.

Decision: Keep public profiles accessible for users without published articles and render an empty state.

Notes: Comment-to-profile navigation remains undecided.

### Q103 - Comment-to-Profile Navigation

Question: Should an authenticated commenters nickname and avatar link to their public profile?

Answer: Yes.

Decision: Link authenticated commenter nicknames and avatars to their public profile pages. Anonymous visitor comments have no profile link.

Notes: Administrator dashboard requirements remain undecided.

### Q104 - Administrator Dashboard

Question: Does the administrator need a back-office home dashboard?

Answer: Not for now.

Decision: Do not build an administrator dashboard landing page in the initial release; use direct feature-management entry points instead.

Notes: Comment-management interface requirements remain undecided.

### Q105 - Comment Management Interface

Question: Does the author need a dedicated interface to view and handle comments in the 10-minute buffer?

Answer: Yes. Manage comments as cards. One tab shows comments currently within the 10-minute buffer. Another view groups by article title, and opening an article title manages that articles comments.

Decision: Build a card-based comment-management interface with a buffered-comments tab and an article-grouped navigation view that drills into per-article comment management.

Notes: Additional comment-management tabs remain undecided.

### Q106 - Additional Comment Management Tabs

Question: Besides buffered comments and article-grouped management, which other comment-management tabs are needed?

Answer: None for now; retain extensibility.

Decision: Ship only the buffered-comments and article-grouped views initially, with an extensible tab structure for future management views.

Notes: Display behavior for author-deleted comments remains undecided.

### Q107 - Deleted Comment Display

Question: After the author deletes a comment, should it vanish completely or show a placeholder?

Answer: Show text stating that the comment has been deleted.

Decision: Preserve the comments position in the thread and render a 该评论已删除 placeholder after author deletion.

Notes: Whether users may reply to a deleted-comment placeholder remains undecided.

### Q108 - Replies to Deleted Comments

Question: May users reply to a deleted-comment placeholder?

Answer: No.

Decision: Disable reply creation for deleted comments.

Notes: Self-service editing and deletion of a users own comments remain undecided.

### Q109 - User-Owned Comment Controls

Question: May authenticated users edit or delete their own comments?

Answer: They may not edit their own comments, but they may delete them.

Decision: Disable self-service comment editing and allow authenticated users to delete only their own comments.

Notes: Display behavior for self-deleted comments remains undecided.

### Q110 - Self-Deleted Comment Display

Question: After a user deletes their own comment, should the same deleted-comment placeholder be shown?

Answer: Yes, retain the placeholder.

Decision: Render the same 该评论已删除 placeholder whether deletion was performed by the author or by the authenticated commenter.

Notes: Anonymous-comment rate limiting remains undecided.

### Q111 - Anonymous Comment Rate Limit

Question: After an unauthenticated visitor posts a comment, how long must they wait before posting again?

Answer: 5 minutes.

Decision: Enforce a 5-minute minimum interval between anonymous comment submissions.

Notes: Authenticated-user comment rate limit remains undecided.

### Q112 - Authenticated Comment Rate Limit

Question: What minimum interval applies between comments from an authenticated user?

Answer: A 1-minute cooldown.

Decision: Enforce a 1-minute minimum interval between authenticated comment submissions.

Notes: Comment length limit remains undecided.

### Q113 - Comment Length and Images

Question: What is the maximum length of a comment?

Answer: 100 characters. Top-level comments may attach up to 3 images; replies may not attach images.

Decision: Limit every comment to 100 characters. Permit up to three image attachments on a top-level comment and prohibit image attachments on replies.

Notes: Comment-image formats and size limits remain undecided.

### Q114 - Comment Image Upload Rules

Question: Which formats may comment images use?

Answer: Use the same formats and size requirements as article covers.

Decision: Accept comment images in PNG, JPEG/JPG, GIF, and WebP formats, each at most 5 MB with unrestricted resolution.

Notes: Server-side storage organization for comment images remains undecided.

### Q115 - Comment Image Storage and Global Size Override

Question: How should comment images be stored on the server?

Answer: Store them by their parent article. Also reduce every single-image maximum to 2 MB.

Decision: Store comment-image media under the parent articles storage area. Supersede all earlier 5 MB per-image limits: covers, inline images, avatars, and comment images each have a 2 MB maximum going forward.

Notes: Cleanup timing for images attached to a deleted comment remains undecided.

### Q116 - Deleted Comment Image Cleanup

Question: When a comment with images is deleted, should its images be removed immediately or retained for a period?

Answer: Delete them immediately.

Decision: Immediately remove all media attachments when their parent comment is deleted.

Notes: Comment-reporting feature remains undecided.

### Q117 - Comment and Reply Reporting

Question: Do users need a feature to report comments?

Answer: Yes. Provide several main report labels chosen by you. Add a report-review tab to administrator comment management. If a report is upheld, delete the comment or reply and show the deletion placeholder, then notify the reporter and reported person in-site. If the report is rejected, notify the reporter.

Decision: Implement reporting for comments and replies with a curated set of standard report reasons. Add an administrator report-review tab. An upheld report deletes the target into the standard placeholder and notifies both parties; a rejected report notifies the reporter.

Notes: Whether the reported user can see the reporters identity remains undecided.

### Q118 - Reporter Identity Privacy

Question: When the reported person is notified of an upheld report, may they see the reporters identity?

Answer: No.

Decision: Keep reporter identity hidden from the reported person in report-outcome notifications.

Notes: Whether unauthenticated visitors may submit reports remains undecided.

### Q119 - Anonymous Reply and Reporting Permissions

Question: May unauthenticated visitors report comments or replies?

Answer: No. Unauthenticated visitors cannot reply or report; they may only publish comments.

Decision: Restrict replies and reports to authenticated users. When an articles comment-login requirement is disabled, unauthenticated visitors may submit top-level comments only.

Notes: Per-user duplicate-report rule remains undecided.

### Q120 - Duplicate Reports and Appeal

Question: How many reports may the same authenticated user submit against the same comment or reply?

Answer: One. After receiving an in-site notification, the user may challenge the report, add materials and a description, and send it back to administrator review.

Decision: Limit each reporter to one initial report per target. Support a post-notification appeal that lets the relevant user supplement evidence and description, creating a new administrator review cycle.
Notes: Which party or parties may submit a report-outcome appeal remains undecided.

### Q121 - Report Appeal Eligibility

Question: After a report outcome, which parties may submit an appeal?

Answer: Each side may appeal once in the outcome that affects them: the reporter may appeal when the report fails, and the reported person may appeal when the report succeeds.

Decision: Permit one appeal per report outcome: reporter-only after rejection, reported-person-only after an upheld report.

Notes: Whether the appeal-review decision is final remains undecided.

### Q122 - Appeal Finality

Question: Is the appeal-review decision final, with no further appeal allowed?

Answer: Yes.

Decision: Treat the appeal-review decision as final and disallow any further appeal for that report.

Notes: Allowed evidence types for a report appeal remain undecided.

### Q123 - Report Appeal Evidence

Question: What types of material may a user add when appealing a report outcome?

Answer: Text up to 200 characters and screenshots, using the sites standard image format and size rules.

Decision: Allow an appeal statement of up to 200 characters plus screenshot attachments. Apply the global image rules: PNG, JPEG/JPG, GIF, or WebP, each at most 2 MB.

Notes: Maximum screenshot count per appeal remains undecided.

### Q124 - Appeal Screenshot Limit

Question: How many screenshots may one report appeal include?

Answer: Three.

Decision: Limit each report appeal to three screenshot attachments.

Notes: Initial-report supplementary-description rule remains undecided.

### Q125 - Initial Report Details

Question: May a user add a supplementary description when first reporting a comment or reply?

Answer: The initial report selects a label, may include up to 200 characters of description, and may upload up to 3 images under the same rules.

Decision: Require one predefined report reason, then allow an optional 200-character description and up to three attachments using the global image rules. The curated report reasons are spam or advertising, abuse or harassment, illegal or dangerous content, privacy disclosure, irrelevant content, and other.

Notes: Invitation-code management details remain undecided.

### Q126 - Invitation Code Batch Generation

Question: Should administrators add identifying notes to invitation codes?

Answer: No. The administrator enters a number to generate that many codes, up to 1,000 at once. The code-generation algorithm is delegated to you.

Decision: Omit invitation-code notes. Support batch generation of 1 to 1,000 codes per request. Generate each code with a cryptographically secure random source as a 16-character Crockford Base32 string, backed by a uniqueness constraint.

Notes: Manual revocation of unused invitation codes remains undecided.

### Q127 - Invitation Code Revocation

Question: May the administrator manually revoke unused invitation codes?

Answer: Yes, both individually and by selecting multiple codes in bulk.

Decision: Allow individual and bulk revocation of unused invitation codes from the administrator interface.

Notes: Revoked invitation-code retention in the management history remains undecided.

### Q128 - Invitation Code History and Status

Question: Should revoked invitation codes remain in the administrator management history?

Answer: Yes. Show revoked status for revoked codes, expired status for codes that time out, and used status for redeemed codes. Opening a used code shows the registered account that used it.

Decision: Retain invitation-code records and expose revoked, expired, used, and active states. Let the administrator open a used-code record to view its redeemed account.

Notes: Invitation-code status filtering remains undecided.

### Q129 - Invitation Code Status Filtering

Question: Should invitation-code management support filtering records by status?

Answer: Yes.

Decision: Provide status filters in the invitation-code management interface.

Notes: Administrator user-list search and filtering remain undecided.

### Q130 - User Management Search

Question: Should administrator user management support search and filtering by email, nickname, or account status?

Answer: Support search and filtering by email and nickname.

Decision: Provide email and nickname search/filter controls in administrator user management.

Notes: Account-status filtering remains undecided.

### Q131 - User Status Filtering and Disable Action

Question: Should the administrator user list support filtering by normal and disabled account status?

Answer: Yes. Management can directly disable a specified account.

Decision: Add normal/disabled status filters to user management and allow direct account disablement from that interface.

Notes: Account re-enablement remains undecided.

### Q132 - Account Re-enablement

Question: May the administrator re-enable a disabled account?

Answer: Yes.

Decision: Allow the administrator to restore a disabled account to active sign-in status.

Notes: Existing-session behavior when an account is disabled remains undecided.

### Q133 - Session Revocation on Account Disablement

Question: When the administrator disables an account, should all existing login sessions for that account become invalid immediately?

Answer: Yes.

Decision: Immediately revoke every active session for an account when it is disabled.

Notes: Disabled-account message and reason visibility remain undecided.

### Q134 - Disabled Account Login Message

Question: When a disabled user tries to sign in, should the site display an administrator-provided disablement reason?

Answer: No. Display only that the account has been disabled.

Decision: Show a generic 该账号已被禁用 sign-in message and do not expose a disablement reason.

Notes: Search-engine indexing policy remains undecided.

### Q135 - Public Article Search Indexing

Question: May publicly visible articles be indexed by external search engines?

Answer: Yes.

Decision: Permit external search-engine indexing for public articles. Keep authenticated and private content out of indexing and the public sitemap.

Notes: Per-article SEO metadata controls remain undecided.

### Q136 - Automatic SEO Metadata

Question: Should the author configure a separate SEO title and search description for each article?

Answer: No. Use the article title for search. Automatically use the first 100 body characters as the summary, or all body text if shorter.

Decision: Do not expose per-article SEO metadata settings. Use the article title as SEO title and derive description from the first 100 body characters, or the full body when shorter.

Notes: Article URL-generation rule remains undecided.

### Q137 - Article Permanent Link ID

Question: Should article permanent links use the article ID, title text, or another rule?

Answer: Use the article ID. The article-ID algorithm is delegated to you.

Decision: Use a URL-safe ULID as the public article identifier and permanent-link key. Its time-sortable immutable ID keeps links stable when titles change.

Notes: RSS subscription support remains undecided.

### Q138 - RSS Feed

Question: Does the blog need to provide an RSS feed?

Answer: Not for now.

Decision: Do not implement RSS subscription in the initial release.

Notes: External analytics integration remains undecided.

### Q139 - Traffic Analytics

Question: Should the blog integrate a third-party traffic analytics service?

Answer: Integrate Umami.

Decision: Deploy and integrate self-hosted Umami on the blog server for traffic analytics, keeping analytics data under server control.

Notes: Umami dashboard access-control scope remains undecided.

### Q140 - Umami Dashboard Access

Question: Should the Umami analytics dashboard be accessible only to the administrator?

Answer: Only the administrator may access it, integrated into the administrator interface.

Decision: Restrict Umami analytics access to the administrator and expose it through the blog administration interface rather than to ordinary users.

Notes: Production domain decision remains undecided.

### Q141 - Production Domain Availability

Question: Does the blog already have a production domain?

Answer: A domain is planned, but no suitable domain provider or specific domain is available yet.

Decision: Keep domain and HTTPS configuration deployment-ready but unconfigured until a domain and provider are selected.

Notes: Pre-domain testing access method remains undecided.

### Q142 - Pre-Domain IP Testing

Question: May the site be accessed through the server IP address for testing before a domain is available?

Answer: Yes.

Decision: Allow temporary IP-address access for testing until a production domain is configured.

Notes: Network-access restriction for the temporary IP test endpoint remains undecided.

### Q143 - Temporary IP Access Restriction

Question: Should the temporary IP-address test endpoint be accessible only from your local public IP?

Answer: Yes.

Decision: Restrict the pre-domain IP test endpoint to the users local public IP.

Notes: Whether the users local public IP is stable remains undecided.

### Q144 - Local Public IP Stability

Question: Is your local public IP address fixed?

Answer: Yes.
Decision: Treat the users local public IP as stable for the temporary IP-test allowlist.
Notes: Exact allowlisted public IP remains undecided.

### Q145 - Temporary Test Allowlist Address

Question: What fixed public IPv4 address should be allowlisted for temporary IP-based testing?

Answer: 114.55.139.26.

Validation: This address is the blog servers own public IP, not an established public IP for the users Windows client.

Decision: Pending correction. Do not configure this server address as the client-test allowlist.

### Q146 - Correction: Client IP and Hosting Location

Question: Is the Windows client public IP fixed, and where will the blog be hosted?

Answer: The Windows public IP is not fixed. The blog will be deployed on the blog server.

Decision: Supersede Q144: do not rely on a fixed client-IP allowlist. Confirm blog-server deployment and leave pre-domain test access control to a different method.

Notes: The temporary pre-domain access-protection method remains undecided.

### Q147 - Pre-Domain Test Access

Question: Before the production domain is ready, what access restriction should protect IP-address testing?

Answer: No restriction; open testing.

Decision: Expose the temporary IP-based test site publicly without an IP allowlist or other access restriction.

Notes: Database backup retention remains undecided.

### Q148 - Database Backup Retention

Question: How long should database backups be retained?

Answer: One month.
Decision: Retain database backups for 30 days.
Notes: Database backup frequency remains undecided.

### Q149 - Database Backup Frequency

Question: How often should database backups run?

Answer: Once per week.
Decision: Run an automated database backup weekly and retain each backup for 30 days.
Notes: Backup storage location remains undecided.

### Q150 - Backup Storage Location

Question: Should database backup files remain only on the blog server or synchronize elsewhere?

Answer: Keep them locally for now. Later adjust this, with administrator-managed configuration to choose the backup target.
Decision: Store backups locally in the initial release and design administrator-managed backup-destination configuration for future external targets.
Notes: Whether media files are included in backup remains undecided.

### Q151 - Media Backup Inclusion

Question: Should article covers, inline images, avatars, and comment images also be included in backups?

Answer: Yes.
Decision: Include all managed media assets in the backup scope alongside the database.
Notes: Media-backup schedule and retention alignment remain undecided.

### Q152 - Media Backup Schedule

Question: Should media backups also run weekly and retain for 30 days?

Answer: Use the same standard.
Decision: Back up managed media weekly and retain media backups for 30 days, aligned with database backups.
Notes: Article-body storage architecture remains undecided.

### Q153 - Alternative Article-Body Storage Proposal

Question: Is storing article body files under user folders, with database paths and a content cache, preferable to storing article bodies in PostgreSQL?

Answer: The user proposes file-based body storage under user-specific folders, database path references, and caching for speed and I/O control.
Decision: Adopt PostgreSQL as the canonical store for article bodies, drafts, published revisions, version history, and permissions. Keep only media in server directories. Add rendered-content caching only when justified by observed performance.
Notes: Initial Redis deployment decision remains undecided.

### Q154 - Initial Redis Deployment

Question: Should the initial release deploy Redis as a cache service?

Answer: Yes.
Decision: Deploy Redis in the initial stack.
Notes: Redis use beyond rendered-content caching remains undecided.

### Q155 - Redis Short-Lived Security State

Question: Besides rendered-content caching, should Redis store verification codes, comment cooldowns, and login-rate-limit state?

Answer: Yes.
Decision: Use Redis for rendered-content caching and short-lived security or rate-control state, including verification codes, comment cooldowns, and login throttling.
Notes: Redis persistence behavior across restart remains undecided.

### Q156 - Redis Restart Persistence

Question: Should Redis short-lived state survive a Redis service restart?

Answer: No, let it be lost.
Decision: Configure Redis as disposable for this workload. A restart may clear caches, verification codes, cooldowns, and rate-limit counters.
Notes: Email-delivery provider for verification codes remains undecided.

### Q157 - Verification Email Delivery Provider

Question: Which email delivery service should send registration, login, and password-reset codes?

Answer: The user requests a recommendation.
Guidance: Use a local Mailpit service during development to capture emails without delivery. After obtaining a domain, choose Resend as the default transactional-email provider for simple API integration and domain authentication; choose Alibaba Cloud DirectMail instead if delivery is primarily to Chinese mailboxes and Alibaba Cloud operations are preferred.
Decision: Use Mailpit for development and test email capture. After a production domain is available, use Resend for transactional verification-email delivery.
Notes: Verification-email sender display name remains undecided.

### Q158 - Configurable Site Name

Question: What sender display name should verification emails show?

Answer: The site name. The administrator can configure it, and it also affects the home-page display and browser-tab title.
Decision: Add an administrator-managed site-name setting. Use it as the verification-email sender display name, home-page brand name, and browser document title source.
Notes: Initial default site name remains undecided.

### Q159 - Initial Site Name

Question: What should the first-release default site name be?

Answer: Kaj的小房间.
Decision: Set the initial default site name to Kaj的小房间.
Notes: Home-page site-description requirement remains undecided.

### Q160 - Optional Site Description

Question: Should the home page display a site description or subtitle?

Answer: Keep the capability. Do not display it when empty; it is currently empty.
Decision: Add an optional administrator-configurable site-description field. Default it to empty and render no subtitle unless it has a value.
Notes: Configurable site-logo requirement remains undecided.

### Q161 - Configurable Site Logo

Question: Does the site need an administrator-configurable logo?

Answer: Yes. Generate a default solid-color letter K logo.
Decision: Add an administrator-configurable site-logo setting. Use a vector or CSS-rendered solid-color K emblem as the default, avoiding an unnecessary bitmap asset.
Notes: Custom logo-upload capability remains undecided.

### Q162 - Custom Site Logo Upload

Question: May the administrator upload a custom logo to replace the default logo?

Answer: Yes.
Decision: Allow an administrator-uploaded custom site logo to override the default K logo.
Notes: Custom logo format and size rules remain undecided.

### Q163 - Custom Logo Formats

Question: Which file formats may be uploaded as a custom site logo?

Answer: ICO and PNG.
Decision: Accept ICO and PNG uploads for custom site logos.
Notes: Custom logo file-size limit remains undecided.

### Q164 - Global Image Upload Standard

Question: What maximum file size applies to a custom site logo?

Answer: Use the same requirements as other images; this is the project-wide image standard.
Decision: Apply a 2 MB maximum to every image upload in the project. Custom logos remain limited to ICO and PNG; other image types retain their previously specified allowed formats.
Notes: Favicon behavior remains undecided.

### Q165 - Favicon Source

Question: Should the custom site logo also be used as the browser-tab favicon?

Answer: Yes.
Decision: Use the active site logo as the favicon; use the default K logo when no custom logo is set.
Notes: Interface-language scope remains undecided.

### Q166 - Interface Language Scope

Question: Which interface languages should the first release support?

Answer: Chinese only for now, while reserving the capability for other languages.
Decision: Ship a Chinese-only interface in the initial release and keep the architecture localization-ready for future languages.
Notes: Mobile and tablet support requirement remains undecided.

### Q167 - Mobile Access

Question: Does the site need to support access from mobile devices and tablets?

Answer: Yes.
Decision: Design and verify the site for responsive mobile and tablet access.
Notes: Mobile administrator-interface scope remains undecided.

### Q168 - Mobile Administrator Interface

Question: Must the administrator interface be fully usable on phones and tablets too?

Answer: Yes.
Decision: Make all administrator workflows responsive and fully operable on mobile and tablet devices.
Notes: Baseline accessibility requirements remain undecided.

### Q169 - Baseline Accessibility

Question: Should the site meet baseline accessibility requirements such as keyboard operation, clear focus indicators, and sufficient text contrast?

Answer: Yes.
Decision: Implement baseline accessibility: keyboard-operable flows, visible focus states, and sufficient text contrast.
Notes: Visual design direction remains undecided.

### Q170 - Visual Direction

Question: What overall visual style should Kaj的小房间 use?

Answer: Minimal and elegant.
Decision: Use a restrained, elegant visual direction that prioritizes reading clarity and information hierarchy.
Notes: Preferred primary color or color family remains undecided.

### Q171 - Primary Color Direction

Question: Which recommended primary color direction should the site use?

Answer: 淡杏酒红.
Decision: Use the 淡杏酒红 palette as the visual baseline. Derive coordinated light, dark, and eye-care modes from it during interface design.
Notes: Reading typography preference remains undecided.

### Q172 - Body Typography

Question: Should body reading typography use a modern sans-serif or book-like serif style?

Answer: 无线, interpreted as 无衬线.
Decision: Use a modern sans-serif typeface for article body reading, optimized for Chinese, English, and mobile clarity.
Notes: Heading typeface relationship remains undecided.

### Q173 - Heading Typography

Question: Should article headings and the site title use the same sans-serif typeface as the body?

Answer: Yes.
Decision: Use one consistent sans-serif typeface family for body text, article headings, and site branding.
Notes: Source-control setup remains undecided.

### Q174 - Local Git Repository

Question: Should /home/code/personal-blog/ be initialized as a local Git repository for code and configuration history?

Answer: Yes.
Decision: Initialize a local Git repository during implementation. Do not perform Git initialization or commits during the requirements interview.
Notes: Remote Git hosting requirement remains undecided.

### Q175 - Remote Git Repository

Question: Does the project need a remote Git host?

Answer: git@github.com:WeirdSky924/Kaj-blog.git.
Decision: During implementation, configure git@github.com:WeirdSky924/Kaj-blog.git as the projects GitHub SSH remote after local repository initialization. Do not connect, commit, or push during the requirements interview.
Notes: Long-term default development branch remains undecided.

### Q176 - Long-Term Development Branch

Question: What should the projects long-term default development branch be?

Answer: Develop directly on master. Unless another branch is explicitly named, use master.
Decision: Use master as the long-term default development branch. Do not create or switch to other branches unless the user explicitly requests one.
Notes: Commit cadence remains undecided.

### Q177 - Git Commit and Push Authorization

Question: At what point should the project create Git commits?

Answer: Commits and pushes are invoked only by the user. When invoked, the commit must carefully cover all feature modules completed in that round.
Decision: Do not create commits or push automatically. Only commit or push after explicit user request, with a carefully scoped message covering the completed modules for that round.
Notes: Commit-message language and format remain undecided.

### Q178 - Commit Message Language

Question: Should Git commit messages use Chinese, English, or a specified format?

Answer: Chinese.
Decision: Write Git commit messages in Chinese.
Notes: Automatic deployment after Git push remains undecided.

### Q179 - Deployment Authorization

Question: Should a push to GitHub automatically deploy to the blog server?

Answer: Deployment is also invoked only by the user.
Decision: Do not auto-deploy after pushes. Run any deployment only after explicit user request.
Notes: Database-migration behavior during an explicitly invoked deployment remains undecided.

### Q180 - Deployment Database Migration

Question: During an explicitly invoked deployment, should database migrations run automatically?

Answer: Synchronize the database when there are updates; if there are no updates, do not run migration updates.
Decision: During an approved deployment, detect pending schema migrations and apply them only when needed; skip migration work when schema is already current.
Notes: Deployment behavior after a migration failure remains undecided.

### Q181 - Migration Failure Handling

Question: If a database migration fails, should deployment stop and retain the current production version?

Answer: Yes.
Decision: Abort deployment on migration failure and retain the current running application version.
Notes: Pre-migration backup requirement remains undecided.

### Q182 - Pre-Migration Backup

Question: Before each database migration, should deployment create an immediate database backup?

Answer: Yes.
Decision: Require a fresh database backup before applying any deployment-time migration.
Notes: Post-deployment health-check requirement remains undecided.

### Q183 - Post-Deployment Health Check

Question: Should deployment automatically run a health check and report deployment failure if it fails?

Answer: Yes.
Decision: Run an automatic post-deployment health check and mark/report the deployment as failed when the check does not pass.
Notes: Automatic rollback after health-check failure remains undecided.

### Q184 - Automatic Application Rollback

Question: Should a failed post-deployment health check automatically roll back to the previous application version?

Answer: Yes.
Decision: Automatically restore the previous application version after health-check failure. Do not automatically reverse database migrations; design migrations for forward compatibility and safe application rollback.
Notes: Deployment-time maintenance-page policy remains undecided.

### Q185 - Deployment Maintenance Page

Question: May an explicitly invoked deployment display a short maintenance page?

Answer: Yes.
Decision: Permit a temporary maintenance page during approved deployments.
Notes: Maximum maintenance-page duration remains undecided.

### Q186 - Maintenance Page Duration

Question: What maximum duration may the maintenance page be displayed?

Answer: Keep it displayed until maintenance is complete.
Decision: Do not impose a fixed duration. Keep the maintenance page active until deployment completes and passes health checks, or until the failure and rollback flow completes.
Notes: Production-secret storage approach remains undecided.

### Q187 - Production Secret Storage

Question: How should production database passwords, email keys, and other secrets be stored?

Answer: Store them in .env and do not upload them to the Git repository.
Decision: Store production secrets in a server-side .env file excluded from Git. Commit only a .env.example template with non-secret placeholders.
Notes: Whether the web administrator interface may edit .env configuration remains undecided.

### Q188 - Web Editing of Secrets

Question: May the administrator web interface directly edit sensitive values in .env?

Answer: No. Modify the .env file itself directly.
Decision: Do not expose .env secrets through the web administrator interface. Require direct server-side file editing for secret changes.
Notes: Web administrator access to backup artifacts remains undecided.

### Q189 - Backup Restore Interface

Question: Does the administrator need to download or restore database and media backups through the web interface?

Answer: No. Build backup files, then restore them manually.
Decision: Generate backups automatically but provide no web download or restore controls. Perform restoration manually on the server.
Notes: Administrator-account two-factor authentication remains undecided.

### Q190 - Administrator and Author Account

Question: Does the administrator account need additional two-factor authentication?

Answer: No. Use the same account and password login. The dedicated author account is also the administrator, and can both manage the site and publish as an author.
Decision: Do not add separate two-factor authentication. Model one dedicated account with both administrator and author roles, using the standard account login methods and all author plus management capabilities.
Notes: Commenting behavior for the administrator-author account remains undecided.

### Q191 - Administrator-Author Commenting

Question: Should the administrator-author account comment and reply in the same way as an ordinary authenticated user?

Answer: Yes.
Decision: Allow the administrator-author account to use standard authenticated commenting and reply capabilities in addition to publishing and management roles.
Notes: Administrator audit-log requirement remains undecided.

### Q192 - Administrator Audit Logging

Question: Should the system record audit logs for key administrator actions?

Answer: Yes. Operations need traceability to support post-incident review.
Decision: Record traceable audit logs for administrator actions to support investigation and review.
Notes: Audit-log retention period remains undecided.

### Q193 - Audit Log Retention

Question: How long should administrator audit logs be retained?

Answer: Retain them indefinitely.
Decision: Retain administrator audit logs indefinitely.
Notes: Whether audit logging includes administrator read-only access remains undecided.

### Q194 - Read-Only Audit Events

Question: Should audit logs also record administrator read-only actions such as opening management pages or viewing data?

Answer: No.
Decision: Record state-changing or permission-changing administrator actions only; exclude read-only page and data views. Cover account, article, media, comment, report, tag, invitation-code, notification, site-setting, and backup-setting changes.
Notes: Audit-log management search and filtering remain undecided.

### Q195 - Audit Log Search and Filtering

Question: Should the administrator web interface support searching and filtering audit logs?

Answer: Yes.
Decision: Provide administrator audit-log search and filtering controls.
Notes: Required audit-log filter dimensions remain undecided.

### Q196 - Audit Log Keyword Search

Question: Which conditions should audit-log filtering support?

Answer: Search directly by keyword.
Decision: Provide keyword search over non-sensitive audit fields such as operation type, target identifier, and summary. Never index or display secret values.
Notes: Before-and-after change detail in audit records remains undecided.

### Q197 - Audit Before-and-After Detail

Question: Should audit-log details record the before-and-after content of each operation?

Answer: Yes.
Decision: Record before-and-after change detail for administrator state-changing actions, subject to the existing prohibition on secrets.
Notes: Audit treatment for large article bodies and media-reference changes remains undecided.

### Q198 - Large-Field Audit Detail

Question: Should article bodies and media references be stored in full in audit logs, or only as version and summary references?

Answer: Record only version number.
Decision: For article bodies and media-reference changes, record only the associated article-version identifier in audit logs; rely on retained version history for detailed content recovery.
Notes: Application runtime-error logging remains undecided.

### Q199 - Application Error Logging

Question: Should the system independently record application runtime error logs for service troubleshooting?

Answer: Yes.
Decision: Implement independent application runtime-error logging for diagnosis and operational troubleshooting.
Notes: Runtime-error-log retention remains undecided.

### Q200 - Runtime Error Log Retention

Question: How long should application runtime error logs be retained?

Answer: Permanently.
Decision: Retain runtime error logs indefinitely.
Notes: Web administrator access to runtime error logs remains undecided.

### Q201 - Web Runtime Error Logs

Question: Should the administrator web interface provide viewing and search for runtime error logs?

Answer: Yes.
Decision: Provide an administrator-only web interface to view and search runtime error logs.
Notes: Sensitive-data masking in error logs remains undecided.

### Q202 - Error Log Sensitive-Data Masking

Question: Must passwords, tokens, verification codes, and other sensitive data be hidden in error logs?

Answer: Hide sensitive information.
Decision: Redact sensitive data from runtime error logs and administrator log views.
Notes: End-user error-message detail remains undecided.

### Q203 - End-User Error Messages

Question: Should ordinary users see generic messages or detailed system errors when something fails?

Answer: Generic message with a code that the administrator can use to query the specific issue.
Decision: Show ordinary users a generic error message plus a traceable error reference code. Keep diagnostic details administrator-only in runtime error logs.
Notes: Initial administrator-author account creation remains undecided.

### Q204 - Initial Administrator-Author Creation

Question: How should the administrator-author account be created at first deployment?

Answer: Write a default account into the database during deployment, then let the deployer directly modify the default information in the database to create it.
Decision: Seed one administrator-author account during first deployment and allow its initial account data to be set directly in the database by the deployer. Store only a password hash; never commit or store plaintext default credentials.
Notes: Default direct-registration switch state at first deployment remains undecided.

### Q205 - Initial Registration and Administrator Password

Question: What should the initial direct-registration setting and administrator password setup be?

Answer: Direct registration should default to disabled. The user requested a fixed initial administrator password and a forced password-change prompt after first login.
Security validation: Do not persist or implement a fixed predictable bootstrap password. It would be unsafe for a publicly reachable deployment and must not be written to this record.
Decision: Default direct registration to disabled. Require first-login password change, but leave the secure initial-secret bootstrap method pending.

### Q206 - Rejected Fixed Bootstrap Password

Answer: The user reiterated the request for a fixed predictable bootstrap password.
Security validation: Rejected. A known bootstrap password can be used by an attacker before the intended administrator first signs in; mandatory later password change does not mitigate that race.
Decision: Do not implement or record a fixed bootstrap password. Keep direct registration disabled and require a non-predictable deployment-time initial secret.

### Q207 - Secure Initial Administrator Secret

Question: Should initial administrator setup use a one-time, random, high-strength INITIAL_ADMIN_PASSWORD in the server .env, followed by forced password change?

Answer: Yes.
Decision: Read a non-predictable INITIAL_ADMIN_PASSWORD from the server-only .env during first initialization and require the administrator to change it on first login.
Notes: Post-initialization invalidation of the bootstrap secret remains undecided.

### Q208 - Bootstrap Secret Invalidation

Question: After the administrator account is initialized, should the .env bootstrap password become invalid automatically?

Answer: Invalidate it.
Decision: Mark the bootstrap secret consumed after first initialization and never use it again for authentication.
Notes: Privacy-policy and terms-of-use requirements remain undecided.

### Q209 - Privacy Policy and Terms Placeholder

Question: Do registered users need privacy-policy and terms-of-use pages?

Answer: Reserve the space; leave it empty for now.
Decision: Add configurable placeholder support for privacy-policy and terms-of-use pages, with no initial content.
Notes: Registration-consent behavior while legal pages are empty remains undecided.

### Q210 - Empty Legal-Page Registration Behavior

Question: While privacy-policy and terms pages are empty, must registration display and require a consent checkbox?

Answer: Hide them for now; no consent checkbox is required.
Decision: Do not display empty legal-page links or registration-consent controls until their content is configured.
Notes: Backend web-framework confirmation remains undecided.

### Q211 - Django Framework

Question: Should the blog use Django as its backend web framework?

Answer: Confirmed.
Decision: Use Django as the backend web framework.
Notes: Production database confirmation remains undecided.

### Q212 - PostgreSQL Database

Question: Should production use PostgreSQL as the database?

Answer: Confirmed.
Decision: Use PostgreSQL as the production database.
Notes: Python runtime version remains undecided.

### Q213 - Python Runtime Version

Question: Should the project use Python 3.12 as its runtime version?

Answer: Confirmed.
Decision: Use Python 3.12 for the project runtime.
Notes: Docker Compose orchestration confirmation remains undecided.

### Q214 - Docker Compose Service Stack

Question: Should Docker Compose orchestrate the application, PostgreSQL, Redis, Umami, and Mailpit?

Answer: Confirmed.
Decision: Use Docker Compose to orchestrate Django, PostgreSQL, Redis, Umami, and Mailpit services.
Notes: Reverse-proxy and HTTPS-termination choice remains undecided.

### Q215 - Caddy Reverse Proxy

Question: Should Caddy serve as the reverse proxy and future HTTPS termination layer?

Answer: Confirmed.
Decision: Use Caddy as the reverse proxy and HTTPS termination layer when a production domain is configured.
Notes: Python dependency-management tool remains undecided.

### Q216 - Python Dependency Management Proposal

Question: Should Python dependencies and virtual environments use uv?

Answer: The user proposes Conda and requests a recommendation.
Guidance: Conda is viable for a local data-science environment but adds image size, build time, and environment divergence for a Dockerized Django service. Use uv inside containers and production; optionally allow Conda only for local personal tooling.
Decision: Use uv as the project standard for dependency and environment management in containers and production. Conda may be used only as an optional local personal tool and is not part of the runtime.
Notes: Test-tooling confirmation remains undecided.

### Q217 - Test Tooling

Question: Should the project use pytest for backend tests and Playwright for browser user-flow tests?

Answer: Confirmed.
Decision: Use pytest for backend and database behavior tests and Playwright for end-to-end browser workflows.
Notes: Code-quality tooling remains undecided.

### Q218 - Python Code Quality Tooling

Question: Should the project use Ruff for Python formatting and static checks?

Answer: Confirmed.
Decision: Use Ruff for Python formatting and static code-quality checks.
Notes: Rich-text editor implementation remains undecided.

### Q219 - Rich-Text Editor

Question: Should rich-text articles use the TipTap editor?

Answer: Confirmed.
Decision: Use TipTap for rich-text article editing.
Notes: Frontend styling tool confirmation remains undecided.

### Q220 - Tailwind CSS

Question: Should frontend styling use Tailwind CSS?

Answer: Confirmed.
Decision: Use Tailwind CSS for frontend styling.
Notes: HTMX and Alpine.js interaction-layer confirmation remains undecided.

### Q221 - HTMX and Alpine.js

Question: Should the project use HTMX and Alpine.js for local interactions?

Answer: Confirmed.
Decision: Use HTMX and Alpine.js for local interactive behavior while retaining server-rendered page architecture.
Notes: Django-template rendering confirmation remains undecided.

### Q222 - Django Template Rendering

Question: Should pages primarily use Django Templates for server-side rendering?

Answer: Confirmed.
Decision: Use Django Templates as the primary server-side rendering layer.
Notes: Application-server choice remains undecided.

### Q223 - Gunicorn Application Server

Question: Should Gunicorn run the Django application?

Answer: Confirmed.
Decision: Run the Django application with Gunicorn behind Caddy.
Notes: Initial Celery worker and scheduler deployment remains undecided.

### Q224 - Initial Background Task Services

Question: Should the initial release deploy Celery worker and Celery Beat for scheduled publication, comment buffering, cleanup, and backup tasks?

Answer: Confirmed. The user also changes the interview cadence: ask all closely related questions together by subject.
Decision: Deploy Celery worker and Celery Beat in the initial stack. Replace the one-question protocol with subject-based rounds that group closely related decisions and still wait for the user response before moving to another subject.
Notes: Background-task failure and retry policy remains undecided.

### Q225 - Background Task Failure Policy

Questions: Should background tasks retry automatically; what happens after the retry limit; and should administrators manually rerun failed tasks?

Answer: Retry automatically three times. After repeated failure, write an error and send an in-site notification to the administrator. Do not provide manual rerun because persistent failure indicates a bug or non-code fatal issue that needs repair.
Decision: Retry failed background tasks up to three times with increasing delays. On final failure, write a runtime error log and notify the administrator in-site. Do not provide web manual-retry controls.
Notes: Password-login abuse-protection policy remains undecided.

### Q226 - Password Login Temporary Restriction

Questions: How many wrong password attempts trigger restriction; how long does it last; and what does the user see?

Answer: Restrict after five failures for one hour. Show that the account is temporarily restricted. The administrator may clear the restriction early.
Decision: After five consecutive password-login failures per email, impose a one-hour login restriction. Show a clear temporary-restriction message and provide an administrator action to remove it early.
Notes: Restriction scope across email-code login and password reset remains undecided.

### Q227 - Temporary Restriction Scope

Questions: Does the temporary restriction block email-code login; may the user reset password while restricted; and is a notification sent when it expires?

Answer: Email-code login is also blocked. Password reset is not allowed. No notification is sent when the restriction ends.
Decision: Apply the one-hour temporary restriction to password login, email-code login, and password reset. End it silently after expiry unless an administrator clears it earlier.
Notes: Verification-code request volume limits remain undecided.

### Q228 - Verification-Code Request Volume Limits

Questions: What are the 24-hour verification-code request limits per email and per public IP; and what happens when they are exceeded?

Answer: 20 per email and 20 per IP. Temporarily prohibit further requests; an administrator can reset the restriction for an account.
Decision: Limit verification-code sends to 20 per email and 20 per public IP in a 24-hour window. Temporarily block sends after either limit is exceeded and permit administrator account-level reset.
Notes: Exact temporary-block duration and IP-level reset policy remain undecided.

### Q229 - Verification-Code Block Expiry and Messaging

Questions: How long do verification-code request blocks last; may an administrator clear IP blocks; and what message should the user see?

Answer: Reset daily at 00:00. The administrator can clear them. Show a clear frequency-limit message.
Decision: Reset email and IP verification-send limits at 00:00 Asia/Shanghai each day. Allow administrator clearing of either account or IP restriction. Show an explicit 验证码请求过于频繁 message.
Notes: Image-upload privacy and safety processing remains undecided.

### Q230 - Image Upload Privacy and Validation

Questions: Should uploads strip metadata; verify real file type; and preserve GIF animation?

Answer: Strip metadata, verify it, and preserve GIF animation.
Decision: Remove EXIF and similar metadata from uploaded images, validate actual file signatures and decoding before storage, and preserve GIF animation behavior.
Notes: Article external-content embedding policy remains undecided.

### Q231 - Article External Content

Questions: May articles add external links, embed external videos or third-party content, and contain author-entered raw HTML?

Answer: Allow all three.
Decision: Support external hyperlinks, third-party content or video embeds, and author-entered HTML. Sanitize all HTML at save and render time with a security allowlist; prohibit scripts, inline event handlers, dangerous URLs, and other active code.
Notes: External-embed source allowlist policy remains undecided.

### Q232 - Trusted Embed Sources and Link Target

Questions: Should embeds use configurable trusted sources; which sources are initially allowed; and how should ordinary external links open?

Answer: Allow configurable trusted sources. Initially permit only Bilibili video. Open external links in a new tab by default.
Decision: Maintain an administrator-configurable embed-source allowlist with Bilibili as the only initial source. Render ordinary external links with a safe new-tab target.
Notes: Behavior of existing embeds when a trusted source is removed remains undecided.

### Q233 - Trusted Source Removal

Questions: When an embed source is removed, how should existing embeds behave; and does the administrator need web management for sources?

Answer: Show a source-unavailable placeholder. The administrator needs web management.
Decision: Replace existing embeds from removed sources with a 来源不可用 placeholder. Provide administrator web controls to add and remove trusted embed sources.
Notes: Article title and summary constraints remain undecided.

### Q234 - Article Title and Card Summary

Questions: What is the title limit; may titles repeat; and how is the article-card summary supplied?

Answer: Titles are at most 30 characters and may repeat. Authors may supply a separate summary; if omitted, they may hide it or use the first 100 body characters.
Decision: Limit titles to 30 characters without uniqueness requirement. Support an optional author-written card summary; when absent, let the author choose no summary or an automatic first-100-character body excerpt.
Notes: Article-card metadata display remains undecided.

### Q235 - Article List Card Metadata

Question: Which metadata should article cards on home, section, and tag-result lists display?

Answer: Display all proposed fields.
Decision: Show cover image, title and summary, section and tags, publication time, view count, and comment count on article cards, subject to article visibility permissions.
Notes: Footer and site-information requirements remain undecided.

### Q236 - Footer Site Information

Questions: Should the footer show site name and current year; reserve configurable copyright; and show legal links once content exists?

Answer: All are needed.
Decision: Show site name and current year in the footer, add administrator-configurable copyright text, and render privacy-policy and terms links after their content is configured.
Notes: Additional public content-page requirements remain undecided.

### Q237 - Additional Public Pages

Questions: Are about, friend-links, and standalone guestbook pages needed?

Answer: All are needed.
Decision: Add public about-site or author, friend-links, and standalone guestbook pages.
Notes: About-page content-management and visibility rules remain undecided.

### Q238 - About Page

Questions: Is the about page edited by the administrator; does it support rich text and Markdown; and is its entry hidden when empty?

Answer: Yes to all.
Decision: Let the administrator edit the about page with rich text or Markdown. Hide its public navigation entry until it has content.
Notes: Friend-link management and display fields remain undecided.

### Q239 - Friend Links

Questions: Who manages friend links; which fields are required; and how do they open?

Answer: Only the administrator manages them. Require site name, URL, description, and logo. Open links in a new tab.
Decision: Restrict friend-link CRUD to the administrator. Require site name, URL, description, and logo; apply global image rules to logos; open friend links in a safe new tab.
Notes: Guestbook publishing and moderation rules remain undecided.

### Q240 - Guestbook Interaction Rules

Questions: May anonymous visitors leave messages; do messages share comment moderation rules; and do they support replies and images?

Answer: Use the same standards as comments.
Decision: Apply the full comment policy to the guestbook: anonymous visitors may submit only top-level messages when allowed; authenticated users may reply and report; preserve the 10-minute buffer, image limits, deletion placeholders, rate limits, and review workflow.
Notes: Public navigation-entry rules remain undecided.

### Q241 - Administrator-Managed Navigation

Questions: How should public navigation, section placement, and logged-in account controls work?

Answer: Keep navigation extensible and administrator-defined. Manage a tree by drag-and-drop in the administrator interface. Any article section can be placed anywhere in this navigation tree, including in or outside a section dropdown. Unauthenticated users see login and registration. Authenticated users see avatar and username, with a hover dropdown for personal management.
Decision: Build a drag-and-drop, tree-structured administrator navigation manager. Do not hardcode section placement. Allow section nodes in arbitrary navigation positions. Show login/registration when unauthenticated; show avatar and username plus hover personal menu when authenticated.
Notes: Fixed entries and administrator-only actions in the personal menu remain undecided.

### Q242 - Notification, Theme, and Personal Menu Placement

Question: Where should notification, theme, and personal-menu actions appear after login?

Answer: Put notifications in a separate floating control to the left of the avatar, with hover notification panel and click-through to the notification page. Put theme switching by the top-left logo and also in personal settings. Put all remaining actions in the personal menu.
Decision: Place notification control left of avatar with hover popover and notification-page navigation. Place a theme switcher at the top-left logo and in account settings. Keep profile, account settings, bookmarks, logout, and administrator management in the personal menu.
Notes: Notification-popover contents and read-state behavior remain undecided.

### Q243 - Notification Popover and Notification Page

Questions: How many notifications appear in the popover; what happens when one is clicked; and how are read states handled on the notification page?

Answer: Show 5. Clicking opens a full floating notification interface rather than navigating. View all navigates to the notification page, which shows all notifications and allows mark-all-read or reading individual notifications to mark them read.
Decision: Show the latest five notifications in the hover popover. Open a full notification overlay when an item is clicked. Make View All navigate to the notification page. On that page, support all-notification listing, explicit mark-all-read, and individual read marking.
Notes: Personal settings page fields and session controls remain undecided.

### Q244 - Personal Settings Capabilities

Question: Should personal settings provide nickname and avatar, email, password, theme, device-session management, and other-device logout controls?

Answer: Provide all.
Decision: Include all listed account-profile, credential, theme, device-session, targeted-session logout, and logout-other-devices controls in personal settings.
Notes: Device-session list details and current-session logout behavior remain undecided.

### Q245 - Device Session Management

Questions: What session details are shown; may current session be exited; and is current session retained when logging out other devices?

Answer: Show device or browser, login time, last activity, and public IP. Current session may be exited. The user also states 退出不保留二次提醒 for the other-device action.
Decision: Display device or browser, login time, last activity, and public IP in session management. Allow explicit current-session logout.
Open point: Clarify whether the other-device action should also terminate the current session, and whether it should run without a confirmation prompt.

### Q246 - Sign Out All Sessions

Question: Does the other-device action also terminate the current session, and should it require confirmation?

Answer: Do not retain the current session, and require a second confirmation.
Decision: Rename the action to 退出所有设备. Terminate every active session including the current one, and require an explicit confirmation dialog before doing so.
Notes: Navigation-node visibility and disablement rules remain undecided.

### Q247 - Navigation Tree Node Rules

Questions: Which node types are supported; may nodes be hidden without deletion; and how do external links open?

Answer: Support all three node types. Nodes may be hidden. External links open in a new tab.
Decision: Support internal-page, article-section, and external-link navigation nodes. Allow administrator hidden state without deletion. Open external-node links safely in a new tab.
Notes: Maximum navigation-tree nesting depth remains undecided.

### Q248 - Navigation Tree Depth and Mobile Expansion

Questions: What is the maximum navigation nesting depth, and how should nested navigation work on mobile?

Answer: Three levels. Show expandable menus on mobile.
Decision: Limit navigation trees to three levels. Render mobile child navigation as expandable menus.
Notes: Registration-page flow for direct-registration and invitation-code modes remains undecided.

### Q249 - Registration Page Modes

Questions: When direct registration is closed, does the registration page remain for invitation code; when open, are both paths shown; and does success auto-login to home?

Answer: Yes to all.
Decision: Keep registration page available for invitation-code registration when direct registration is closed. When open, show both direct and invitation-code paths. After successful registration, automatically sign in and navigate to the home page.
Notes: Registration form ordering for invitation code, email verification, and password remains undecided.

### Q250 - Registration Form Order

Questions: Is password required; should invitation code be validated before email-code sending; and when is password shown relative to email verification?

Answer: Password is required. Validate invitation code first. Registration form includes a separate send-code button; user enters the emailed code and password, then submits registration.
Decision: Require a password at registration. Validate invitation code before sending email verification. Keep password and verification-code fields on the registration form, with separate code-send action and final submit validation.
Notes: Invitation-code consumption and email binding during partial registration remain undecided.

### Q251 - Invitation Code and Registration Email Binding

Questions: When is an invitation consumed; does partial registration preserve it; and is registration code bound to one email?

Answer: Only consume on final success. Keep available during incomplete registration. Bind the code to that email.
Decision: Consume invitation codes only after successful account creation. Leave them active during incomplete registration. Bind every registration verification code to the email used when it was sent.
Notes: Login-page entry and layout rules remain undecided.

### Q252 - Login Page Layout

Questions: Are login methods tabs on one page; is 30-day remember shown for both; and is forgot-password limited to password login?

Answer: Same-page tabs, show it for both, and yes.
Decision: Use one login page with password and email-code tabs. Show the 30-day remembered-login control in both. Show forgot-password only on the password-login tab.
Notes: Administrator site-settings organization remains undecided.

### Q253 - Administrator Site Settings Area

Question: Should site branding, appearance and registration, navigation and embeds, legal pages, backup target settings, and Umami entry be centralized in grouped site settings?

Answer: Yes.
Decision: Provide a centralized administrator site-settings area with grouped configuration for all listed categories.
Notes: Default visibility for newly created articles remains undecided.

### Q254 - New Article Defaults

Questions: What are default visibility, status, and comment setting for a new article?

Answer: Public visibility, draft status, and comments enabled.
Decision: Default new articles to public visibility, draft state, and comments enabled.
Notes: Visibility-change behavior for published articles remains undecided.

### Q255 - Published Article Visibility Change

Questions: May authors change published visibility; does it take effect immediately; and are downgraded public articles removed from discovery surfaces?

Answer: Yes, immediately, and remove them immediately.
Decision: Allow post-publication visibility changes with immediate enforcement. Immediately remove public-to-authenticated or private articles from site search, tag and section lists, and sitemap.
Notes: Article-section metadata and deletion behavior remain undecided.

### Q256 - Article Section Metadata and Deletion

Questions: Which fields does a section need; must its name be unique; and what happens to assigned articles when a section is deleted?

Answer: Name only. Names cannot repeat. Do not delete articles; transfer them to an unknown section where they are discoverable only from home and tags.
Decision: Give sections a unique name only. On section deletion, retain assigned articles and move them to an unknown-section state. Exclude that state from section navigation and section lists while retaining home and tag discovery.
Notes: Administrator deletion behavior for global tags remains undecided.

### Q257 - Global Tag Deletion

Questions: What happens to used tags on deletion; is history retained; and what do old tag links show?

Answer: Remove them from articles. Retain records for restoration. Show empty result.
Decision: When an administrator deletes a global tag, remove it from all related articles. Preserve its historical record for restoration. Render old tag links as empty results.
Notes: Restored-tag behavior for previously removed article associations remains undecided.

### Q258 - Restored Tag Associations

Question: When an administrator restores a deleted tag, should earlier article associations be restored automatically?

Answer: Restore automatically.
Decision: Restore the tags prior associations to articles automatically when the tag is restored.
Notes: Comment-thread display ordering and deep-thread behavior remain undecided.

### Q259 - Comment Display and Sorting

Questions: What are default top-level and reply orders; how are long reply chains collapsed; and which comment sort modes exist?

Answer: Earliest first for both. Collapse after 10 replies; each expansion shows 10 more. Support latest, earliest, and hottest sort modes.
Decision: Default top-level comments and replies to chronological ascending order. Collapse each reply chain after 10 replies and expand in increments of 10. Offer latest, earliest, and hottest sort modes.
Notes: Hottest-comment calculation and sort-preference persistence remain undecided.

### Q260 - Hottest Comment and Sort Preference

Questions: How is hottest calculated, and where is comment sort choice stored?

Answer: Sort hottest by reply count. Store selection only in the current browser.
Decision: Rank hottest comments by reply count. Persist each users comment-sort preference only in their current browser.
Notes: Top-level comment pagination or loading behavior remains undecided.

### Q261 - Top-Level Comment Loading

Questions: How many top-level comments load initially; how does more loading work; and how many are added each time?

Answer: Show 20. Load more by scrolling to the bottom, adding 20 each time.
Decision: Initially render 20 top-level comments. Use automatic infinite loading at the bottom of the comment list, adding 20 comments per batch without a manual button.
Notes: Article-editor autosave and recovery behavior remains undecided.

### Q262 - Editor Autosave and Recovery

Questions: Does editor autosave; where is autosave stored; and how does recovery work after interruption?

Answer: Autosave on content changes, locally only. Cloud draft saves only on explicit save. On recovery, use local draft if present; otherwise automatically load cloud draft if available without prompt.
Decision: Debounce content-change local autosave. Sync to cloud only when the user explicitly saves a draft. On editor recovery, automatically restore local draft first, else automatically load the available cloud draft.
Notes: Markdown and rich-text preview behavior remains undecided.

### Q263 - Editor Preview and Final Review

Questions: Does Markdown preview in real time; how is it laid out; does rich text have preview; and is final full-article review required before publishing?

Answer: Real-time side-by-side preview for Markdown and rich text. Enter a full preview for review after submission, and publish only after confirmation.
Decision: Render real-time side-by-side preview for both editor formats. Require a full-article review stage before the author confirms publication.
Notes: Final-review back-to-edit and immediate-versus-scheduled publish actions remain undecided.

### Q264 - Final Review Actions

Questions: May the author return to editing; how does final confirmation choose immediate or scheduled publishing; and what happens when review closes unconfirmed?

Answer: Return is allowed. Choose immediate or scheduled publication. Keep as draft.
Decision: Allow return to editor from final review. Require author selection of immediate versus scheduled publication at final confirmation. Keep unconfirmed review exits as drafts.
Notes: Server persistent-data directory organization remains undecided.

### Q265 - Persistent Data and Environment Directories

Questions: Should runtime data use the proposed project-local var tree outside Git, and should .env remain at project root outside Git?

Answer: Yes to both.
Decision: Use /home/code/personal-blog/var for PostgreSQL, media, backups, and logs, excluded from Git. Keep .env at project root, also excluded from Git.
Notes: Public HTTP and HTTPS port policy remains undecided.

### Q266 - Public HTTP, HTTPS, and Administrator Access

Questions: Use HTTP 80 for pre-domain tests; redirect HTTP 80 to HTTPS 443 after domain setup; and share domain or port for admin access?

Answer: Yes to all.
Decision: Serve pre-domain testing over HTTP 80. After domain setup, enable HTTPS 443 and redirect HTTP 80 to HTTPS. Host administrator routes on the same domain and port, enforcing access through authentication and authorization.
Notes: Public exposure of internal container-service ports remains undecided.

### Q267 - Internal Container-Service Exposure

Questions: Should PostgreSQL, Redis, Mailpit, and Umami avoid public ports; how is Umami reached; and are any extra server ports open?

Answer: Do not expose public access because all services are on one server. Yes, Umami stays internal. Yes, do not open extra ports.
Decision: Keep PostgreSQL, Redis, Mailpit, and Umami on Docker internal networks without public port bindings. Reach Umami only through authenticated blog administration. Expose no server ports beyond SSH 444, HTTP 80, and future HTTPS 443.
Notes: Container restart and post-reboot health policy remains undecided.

### Q268 - Container Restart and Health Policy

Questions: Restart services after server reboot; use service health checks and dependency readiness; restart services after unexpected exit?

Answer: Yes to all.
Decision: Configure automatic Compose service restart after server reboot, Docker health checks with dependency readiness, and automatic restart after unexpected container exit.
Notes: Operational monitoring and alerting scope remains undecided.

### Q269 - Operational Monitoring and Email Alerting

Questions: Monitor service health, disk, backup failures, and final task failures; log and in-site notify; and use an external alert channel when site is unavailable?

Answer: Yes to all. Use the administrators account email for email alerts.
Decision: Monitor application and container health, disk capacity, database backup failures, and final task failures. Log and send in-site administrator alerts. Also send operational-alert emails to the administrators account email. This is an explicit exception to the initial no-nonverification-email rule.
Notes: Alert email frequency, deduplication, and recovery notification behavior remain undecided.

### Q270 - Alert Email Frequency and Disk Threshold

Questions: What is the repeated-alert interval; send recovery emails; and what disk-free threshold triggers alert?

Answer: Send once per hour. No recovery email. Alert below 10 percent free disk.
Decision: Deduplicate repeated alert emails to at most one per hour per ongoing failure. Do not send recovery emails. Trigger disk-capacity alert below 10 percent free space.
Notes: Critical disk-low protective behavior remains undecided.

### Q271 - Critical Disk-Low Protection

Questions: What happens below 5 percent free disk; below 2 percent; and to existing content?

Answer: Pause uploads and show 暂时不支持上传图片 below 5 percent. Below 2 percent, prohibit all new text and image creation site-wide. Existing content remains unaffected.
Decision: Below 5 percent free disk, block image uploads with the stated message. Below 2 percent, block all creation of textual and image content while keeping existing-content reading available.
Notes: Automatic recovery thresholds after disk space is reclaimed remain undecided.

### Q272 - Disk Protection Automatic Recovery

Questions: When disk space rises above 5 and 2 percent, should protections lift automatically, and is manual confirmation needed?

Answer: Automatically lift and restore all restrictions.
Decision: Automatically restore image uploads above 5 percent and textual or image creation above 2 percent, without administrator confirmation.
Notes: Page-cache permission boundary and invalidation policy remains undecided.

### Q273 - Public Page Caching

Questions: Should only public content be cached; should lifecycle changes invalidate immediately; and should dynamic values remain real-time?

Answer: Yes to all.
Decision: Cache only public articles and public list pages. Immediately invalidate related cache on publication, republishing, visibility change, deletion, or restoration. Keep comments, view counts, bookmarks, and other dynamic values real-time.
Notes: Implementation delivery sequencing remains undecided.

### Q274 - Implementation Delivery Sequence

Question: Should development deploy incrementally by stage, or complete all features before one unified deployment and acceptance?

Answer: Complete all features first, then deploy and accept together.
Decision: Complete the full requested feature set before unified deployment and acceptance. Continue internal focused verification during development, but do not deploy incomplete stages.
Notes: Content import and export requirements remain undecided.

### Q275 - Content Import and Export

Questions: Should administrators export articles and versions; import Markdown in bulk; and may ordinary users export their data?

Answer: Yes, yes, and no.
Decision: Provide administrator article-and-version export plus bulk Markdown import. Do not provide ordinary-user export of profile, comment, or bookmark data.
Notes: Article import/export package format and media handling remain undecided.

### Q276 - Import and Export Package Format

Questions: Should export be ZIP with JSON, Markdown, versions, and media; should Markdown import use YAML Front Matter; and should referenced images be copied into media storage?

Answer: Yes to all.
Decision: Export a ZIP package containing JSON metadata, Markdown bodies, version history, and media. Import Markdown using YAML Front Matter for metadata and copy referenced images into article media directories.
Notes: Duplicate and invalid-file behavior during bulk import remains undecided.

### Q277 - Bulk Import Exception Handling

Questions: For duplicate articles, should the import skip, update, or create a new article; should invalid Markdown or image files skip only that article and continue; and should the final result display per-article success, skip, and failure outcomes?

Answer: Let the administrator choose skip, update, or create for each duplicate article. Invalid files should be skipped. Yes, display results.
Decision: During import, provide a per-duplicate choice of skip, update the existing article, or create a new article. When an article Markdown file or referenced image is invalid, skip that article and continue the remaining import. Present a final per-article results view with successful, skipped, and failed outcomes and their reasons.
Notes: Import preview, overwrite/version behavior, and rollback requirements remain undecided.

### Q278 - Import Preview, Identity, and Partial Success

Questions: Should import show a validation preview and require confirmation before writing; how should duplicate articles be identified; should updates retain history; and should successful items remain if other items fail?

Answer: Preview the imported content and let the author confirm it. All authors may import. Identify duplicates by ID; when no ID exists, generate one and compare identical titles, then show a warning. Preserve history after update. Keep successful items; do not roll back the whole batch.
Decision: All authors may use bulk import. After a package is uploaded and parsed, show the imported content preview and require the importing author to confirm before data is written. Treat an existing article ID as a duplicate. When an imported article has no ID, generate a new ID; also detect identical titles and warn the author without treating title equality alone as a duplicate. An update preserves the existing article version history and adds the imported content as a new version. Use partial success: retain successfully processed articles even when other items fail.
Notes: This supersedes Q275's administrator-only Markdown import permission. Imported-content ownership, metadata mapping, per-item preview selection, and same-ID cross-author behavior remain undecided.

### Q279 - Import Ownership and Metadata Mapping

Questions: Who owns imported articles; how should an existing matching ID owned by another author be handled; should article metadata be retained; what happens to missing sections or tags; and may authors select individual preview items and duplicate actions?

Answer: Imported articles belong to the importing author. Warn about suspected matching articles by a different author; if the author proceeds with publication, notify the administrator. Updating or creating against another author's matching ID is prohibited. Preserve imported metadata. If a section is not reselected, move the article to the unknown section. Allow per-item selection and duplicate actions in the preview.
Decision: Every imported article is owned by its importing author, regardless of package authorship metadata. A non-administrator cannot update or create an article when the imported ID belongs to another author. For suspected duplicate content belonging to another author, warn the importing author; if the author continues to publish, create an administrator notification. Preserve article visibility, section, tags, cover, comment settings, publication status, and scheduled publication time. When a package section cannot be mapped and the author does not choose a replacement in preview, assign the article to the unknown section. The preview supports selecting or excluding individual articles and choosing skip, update, or create per duplicate where authorized.
Notes: The exact detection criteria for suspected same-content articles and behavior for imported tags absent from the site remain undecided.

### Q280 - Derived Rules for Imported Title Matches and Tags

Question: How should the existing title-match and author-created-tag rules apply to imported content?

Answer: Resolved from prior decisions; no new user choice required.
Decision: A suspected duplicate is an exact title match, not a body-similarity comparison. For an imported tag absent from the site, create it as a tag proposed by the importing author, attach it to the article immediately, and submit it for administrator review. If rejected, remove the tag from the article and notify the author, consistent with the established author-created-tag workflow.
Notes: This resolves the open items in Q279. Content export permission and selection scope remain undecided.

### Q281 - Content Export Permission and Scope

Questions: Who may export content; may the exporter choose articles and include non-public states and historical content; may administrators filter by scope; and may deleted-cooldown articles be exported?

Answer: Only administrators may export. They may choose content. Yes, administrators may filter by scope. Allow export of articles in the deletion cooldown.
Decision: Content export is administrator-only. Administrators may select the articles to export; export packages include full historical versions and associated media as established in Q276. They may filter an export by the whole site, a specific author, a section, or selected articles. Articles within the seven-day deletion cooldown are exportable.
Notes: Whether drafts, scheduled articles, and private articles are selectable for export remains undecided, as do export-job delivery, artifact retention, and download-access policy.

### Q282 - Export Job Delivery and Retention

Questions: May administrators export drafts, scheduled and private articles; should exports run as background jobs with notifications; how long are download packages retained; and may an administrator cancel an unfinished export?

Answer: Allow all of those article states. Yes, use background jobs and notifications. Retain packages for three days. Allow cancellation.
Decision: Administrators may export drafts, scheduled articles, and private articles. Generate exports asynchronously; notify the administrator through the in-site notification system upon completion or final failure. Retain completed ZIP packages for three days, then automatically remove them. Administrators may cancel an unfinished export task.
Notes: Cancellation cleanup, task concurrency, and export-download authorization details remain undecided.

### Q283 - Export Task Safety and Concurrency

Questions: What happens on cancellation; how many exports may run simultaneously and what happens to additional requests; and who may download completed archives?

Answer: Delete the ZIP and keep the record. One task; reject additional requests. Only the logged-in administrator may download.
Decision: Canceling an export immediately removes its incomplete ZIP while permanently retaining the task audit record. Allow one running export task globally; reject new export requests while one is running rather than queueing them. Completed archives are downloadable only through the authenticated administrator interface, with no public or transferable download links.
Notes: This resolves the export lifecycle and access policy. Account deletion and personal-data retention behavior remain undecided.

### Q284 - Account Deletion and Content Handling

Questions: May users self-request account deletion; how should personal data and comments be handled; and what happens when an author account is deleted while it still owns articles?

Answer: Users may not self-delete. Accept the proposed deletion of personal data and private state. Keep a comment placeholder. When an administrator deletes an author, show a reminder and allow article deletion or preservation through export. After deletion succeeds, delete everything.
Decision: Account deletion is an administrator-only action, with no self-service request or cooling-off workflow. On deletion, remove the account's email, nickname, avatar, sessions, bookmarks, notifications, and other private account data. Preserve historical comments as an anonymous “该账号已注销” placeholder. Before deleting an author account, require the administrator to address its articles and offer export for preservation; once deletion is confirmed, delete the account's articles and associated media as well. Retain the required audit record; deleted-account identity information remains visible in the administrator-only moderation records as resolved in Q287.
Notes: Administrator account-deletion authority, whether any article transfer path is needed, and handling of reports or pending moderation items tied to a deleted account remain undecided.

### Q285 - Role Management Boundaries

Questions: May administrators grant or revoke author status; may users self-upgrade; what happens to articles after author-role revocation; what may authors manage; and may administrators delete themselves?

Answer: Yes, administrators manage author status. Existing articles remain. Authors may manage only their own articles. Administrators are prohibited from self-deletion.
Decision: Administrators may grant or revoke the author role for registered users; users cannot request or self-upgrade to that role. Revoking author status prevents future author actions but preserves the user's existing articles under that user. Authors may create and manage only their own articles and cannot access the administrator interface. An administrator account cannot delete itself.
Notes: The site currently has one administrator. Whether additional administrator accounts can ever be granted, and the final handling of moderation items tied to deleted accounts, remain undecided.

### Q286 - Administrator Account Cardinality

Question: Should the site permanently have only one administrator account, or may the existing administrator grant that role to other users later?

Answer: Limit the site to one administrator.
Decision: The system permanently supports exactly one administrator account. No interface or workflow may grant administrator status to a second account.
Notes: This resolves the remaining administrator-role expansion question. Pending moderation items associated with deleted accounts remain undecided.

### Q287 - Pending Reports for Deleted Accounts

Questions: How should an unresolved report behave when its reporter is deleted; how should it behave when its reported user is deleted; and should report and appeal records retain deleted-account information?

Answer: Automatically close reports from a deleted reporter. Close reports against a deleted user and notify the reporter. Retain the records and display the information.
Decision: When a reporter's account is deleted, automatically close that reporter's unresolved reports. When a reported user's account is deleted, close the report with the outcome “内容已删除” and notify the still-existing reporter. Retain reports and appeals permanently; the administrator-only records continue to display the linked deleted-account information.
Notes: This resolves the final deleted-account moderation workflow.

### Q288 - Backup Verification and Encryption

Questions: Should completed backups be automatically validated; should restore drills run on a schedule; and should local backup archives be encrypted?

Answer: Do not validate. No restore drills. Do not encrypt.
Decision: Do not perform automatic backup-integrity or database-dump readability verification after backup creation. Do not schedule isolated restore drills. Keep local backup archives unencrypted. Existing backup-task failure monitoring and alerting remains the only automated failure signal.
Notes: This resolves backup verification policy; the administrator manually restores a backup when needed.

### Q289 - Account Permission-Change Notifications

Questions: Should author-role grants and revocations notify the user; should account disablement or re-enablement notify the user; and should all of these changes be audited?

Answer: Send role-change notifications. Send neither disablement nor re-enablement notifications. Yes, audit all changes.
Decision: Send an in-site notification when an administrator grants or revokes author status. Do not notify users when accounts are disabled or re-enabled. Permanently audit author-role grants, author-role revocations, account disablement, and account re-enablement.
Notes: Author-role notifications are a later exception to Q068's initial notification-event scope. This resolves notifications for administrator-controlled account status and role changes.

### Q290 - Direct-Link Access to Restricted and Removed Articles

Questions: How should a visitor reach a login-visible article; how should private, unpublished, deletion-cooldown, and permanently removed articles behave for unauthorized direct-link access?

Answer: Show a login-required reminder page with a login button and return after successful login. Show 404 for private articles. Show 404 for all other listed states.
Decision: A guest opening a login-visible article sees a login-required reminder page, not an immediate redirect; its login button preserves the requested article as the post-login destination. Return HTTP 404 for non-author access to private articles and for access to drafts, not-yet-published scheduled articles, articles in the deletion cooling period, and permanently deleted articles. The lost-article message and cover remain exclusive to the user's bookmark list.
Notes: This resolves direct-link authorization and disappearance behavior.

### Q291 - Article Ownership Transfer

Questions: May an administrator transfer an article to another author; may an author initiate such a transfer; and, if so, how should history and notifications behave?

Answer: No. No. Transfer is not permitted.
Decision: Article ownership is immutable. Neither administrators nor authors may transfer an article to another author. Consequently, no ownership-transfer history or notifications are implemented.
Notes: This resolves author ownership changes beyond role revocation and account deletion.

### Q292 - Anonymous Comment Anti-Abuse and IP Blocking

Questions: Should registration or anonymous comments use CAPTCHA; should anonymous comments have an IP daily cap in addition to cooldown; and may administrators block IP addresses from sensitive actions?

Answer: No CAPTCHA. No daily cap. Administrators may block IPs.
Decision: Do not introduce CAPTCHA or other human-verification challenges for registration or anonymous comments. Do not impose an anonymous-comment daily IP quota beyond the established five-minute cooldown. Administrators may block an IP address from registration, login-verification-code requests, and anonymous-comment publication.
Notes: IP-block duration, management controls, user-facing message, and effect on already authenticated users remain undecided.

### Q293 - IP Block Lifecycle and Scope

Questions: How long do IP blocks last; what may a blocked IP still do; what management controls are required; and what message is shown?

Answer: Permanent. It may browse only as a visitor; everything else is prohibited. The management controls are needed. Show the generic message.
Decision: IP blocks remain active indefinitely until an administrator manually removes them. A blocked IP may only browse public content as a visitor; reject all other actions, including authenticated actions. The administration interface lists blocked IPs with creation time and an optional note, supports searching and manual unblocking. Show the generic message “当前网络暂时受限” without exposing the administrator note. IP blocking does not delete the underlying account; it applies to requests originating from the blocked IP.
Notes: Audit-log and anonymous-comment IP retention and visibility remain undecided.

### Q294 - IP Audit Retention and Visibility

Questions: Should security-relevant events retain full client IPs; who may see them; and how long should they be retained?

Answer: Yes. Only administrators may view them; mask them in lists and reveal full values in details. Retain permanently.
Decision: Retain full client IPs for login attempts, verification-code requests, administrator write actions, and anonymous comments. Only the administrator may access these IPs. Mask IP values in ordinary administrative lists and reveal the full value only in the relevant detail view. Retain IP records permanently alongside their associated audit or comment records.
Notes: This resolves IP traceability and retention policy.

### Q295 - Identity Reuse After Account Deletion

Questions: May an account's old email and nickname be reused after deletion; may old comments attach to a later account with the same identity fields; and does every account require a new unique user ID?

Answer: The email may be reused. Release the nickname immediately. Do not associate old content with a new account. Every account has a new, non-duplicated user ID.
Decision: Immediately release a deleted account's email address and nickname for reuse. Keep all historical comments permanently detached from any later account that uses the same email or nickname, retaining only the deleted-account placeholder. Assign every created account an immutable, globally unique, never-reused internal user ID; identity fields never determine historical ownership.
Notes: This resolves identity reuse and historical attribution after account deletion.

### Q296 - Concurrent Article Editing Conflicts

Questions: How should same-author concurrent edits behave; how is a conflict resolved; and what effect does an unresolved editing conflict have on a currently published article?

Answer: Prompt about the conflict and prohibit further editing. The author must choose a specific version to overwrite and continue editing; version details are visible during selection. Editing conflicts do not affect the published version because the editing changes have not been published.
Decision: On detection of an article editing conflict, stop further editing rather than silently overwriting. Present the available versions with their metadata and require the author to select one version as the new editing baseline; only after replacement with that selected version may editing continue. An unresolved conflict affects only unpublished editing state and never changes the article version currently visible to readers.
Notes: This resolves concurrent editing behavior for drafts and unpublished revisions.

### Q297 - Draft Lifecycle and Privacy

Questions: May authors delete cloud drafts immediately; when are local drafts cleared; are cloud drafts cleared after publication; and who may view drafts?

Answer: Yes. Clear local drafts at every listed moment. Automatically delete after publication. Only the author may view them.
Decision: Authors may delete cloud drafts immediately without a cooling period. Clear a local autosaved draft after successful publication, when the related cloud draft is manually deleted, or when the author clears browser data. Automatically remove the related cloud draft after publication. Drafts are visible only to their author; the administrator cannot view another author's drafts.
Notes: This resolves draft deletion, cleanup, and access boundaries.

### Q298 - Historical Article Version Restoration

Questions: What does restoration include; does it preserve version history; and how does restoring a published article reach readers?

Answer: Restore all article content and configuration. Restoration creates a new version. Restoration also requires preview and publication.
Decision: Restore the complete saved article state: title, body, content format, cover, visibility, section, tags, and comment settings. A restoration never overwrites history: it creates a new current version while retaining both the pre-restoration state and the historical source version. Restoring a published article follows the normal final-preview and republishing workflow; readers continue to see the existing published version until the restored revision is explicitly published.
Notes: This resolves version-restoration scope and publication behavior. The user clarified that obvious behavior consistent with established rules should be decided directly; future questions are limited to material unresolved product choices.

### Q299 - Published Articles of a Disabled Author

Question: When an author account is disabled, should its already published articles remain reader-visible or be hidden?

Answer: Hide them.
Decision: Hide every article published by a disabled author from all readers while retaining the article records, version history, and media for later administrator action or account re-enablement. This differs from disabled users' existing comments, which remain visible.
Notes: Whether articles are automatically restored when the author account is re-enabled remains a material unresolved choice.

### Q300 - Article Restoration After Author Re-enablement

Question: When a disabled author account is re-enabled, should its hidden published articles automatically restore their previous visibility or require administrator action per article?

Answer: Automatically restore.
Decision: Automatically restore all articles hidden solely because their author account was disabled, returning each article to its prior visibility state when that author account is re-enabled.
Notes: This resolves the disabled-author article lifecycle.

### Q301 - Scheduled Articles When an Author Is Disabled

Question: If a scheduled article reaches its publication time while its author account is disabled, should it later publish automatically after re-enablement or be canceled to a draft?

Answer: Cancel it to a draft.
Decision: When an author account is disabled, cancel every not-yet-published scheduled article to a draft. Do not automatically publish it after re-enablement; its author must explicitly schedule or publish it again.
Notes: This resolves scheduled-publication behavior across author disablement.

### Q302 - Administrator Article-Management Exception

Question: May the administrator manage articles owned by other authors, including private articles, despite author-only article access?

Answer: The administrator is an exception and may manage all articles.
Decision: The sole administrator may view every article regardless of its author or visibility level, including private articles. This is an explicit administrator exception to the normal author-only access rule for private content. Administrator actions are further limited by Q303.
Notes: Administrator viewing and management scope is resolved by Q303.

### Q303 - Administrator Article Actions and View Notifications

Question: Which management actions may the administrator take on other authors' articles, and what happens when the administrator views an article?

Answer: The management interface may only hide published articles and delete or restore articles. The administrator may view articles, but viewing requires an in-site notification to the author.

Decision: The administrator may view all article states, including private articles, drafts, scheduled articles, and unpublished revisions. Each administrator view of another author's article creates an in-site notification for that author. The administrator may hide only a published article, and may delete or restore articles. The administrator may not edit article content, modify article settings, publish, republish, or schedule another author's article. Administrator deletion and restoration follow the established article deletion cooling-period and restoration rules.
Notes: The authority to restore a temporarily administrator-hidden published article remains undecided.

### Q304 - Restoration of Administrator-Hidden Articles

Question: Who may restore an article hidden by the administrator; what visibility returns; and should hiding or restoration notify the author?

Answer: Only the administrator. Restore the former visibility. Yes, notify the author for both actions.

Decision: Only the administrator may restore a published article that the administrator hid. Restoration returns the article to its exact pre-hide visibility level. Send the author an in-site notification when the administrator hides or restores the article.
Notes: Administrator viewing, hiding, and restoration notifications are later exceptions to Q068's initial notification-event scope. The notification frequency for repeated administrator views remains undecided.

### Q305 - Administrator Article-View Notification Frequency

Question: Should repeated administrator views of the same other-author article notify the author every time or be aggregated?

Answer: At most one per day.

Decision: Aggregate administrator-view notifications per author and article, emitting no more than one in-site notification per Shanghai calendar day regardless of repeated views.
Notes: This resolves administrative article-view notification frequency.

### Q306 - Export Notification to Affected Authors

Question: Should an administrator export that includes another author's articles notify that author?

Answer: Yes, send a notification.

Decision: When an administrator export includes any other author's content, send affected authors an in-site notification. Aggregate notifications per affected author and Shanghai calendar day, with at most one export notification per day even if multiple exports include their content.
Notes: Administrator export notifications are a further exception to Q068's initial notification-event scope.

### Q307 - Derived Notifications for Administrator Article Deletion

Question: How should established administrator article-operation notification and audit rules apply to administrator deletion and restoration of another author's article?

Answer: Resolved from the established administrator article-operation rules; no new user choice required.

Decision: When the administrator deletes or restores another author's article, send the author an in-site notification and permanently audit the action. This aligns with the confirmed hide, unhide, administrator-view, and export traceability rules. Notifications remain stored for disabled authors and become readable if they are later re-enabled.
Notes: This is a derived consistency rule, not a new product capability.

### Q308 - Direct Administrator Comment Deletion

Question: May the administrator directly delete any comment or reply in comment management, rather than only deleting it through a successful report review?

Answer: The administrator may delete it.

Decision: The administrator may directly delete any comment or reply from the comment-management interface. The normal deleted-comment placeholder remains visible and associated comment images are immediately removed, following the established comment-deletion rules.
Notes: Whether direct administrator deletion notifies the commenter or article author remains a material unresolved choice.

### Q309 - Notifications for Direct Administrator Comment Deletion

Question: Who should receive an in-site notification when the administrator directly deletes a comment or reply?

Answer: Notify everyone through the in-site system except anonymous visitor comments.

Decision: For a direct administrator deletion, notify every affected registered user through the in-site notification system, including the comment or reply author and the owning article's author when they are different users. Do not attempt notification for anonymous visitor comments. Deduplicate notices when one user holds multiple affected roles.
Notes: Whether a directly deleted comment has an appeal path, and what reason is exposed in the notification, remain material unresolved choices.

### Q310 - Finality and Reason for Direct Administrator Comment Deletion

Question: May a user appeal direct administrator comment deletion, and what reason should the deletion notification contain?

Answer: Appeals are not allowed. The administrator may fill in a reason; otherwise use a generic deletion message.

Decision: A direct administrator comment or reply deletion is final and has no appeal path. The administrator may provide a deletion reason in the management action; show that reason in related notifications when present, otherwise show the generic deletion message.
Notes: This resolves direct administrator comment-deletion communication and finality.

### Q311 - Appeals and Reasons for Administrator Article Actions

Question: May an author appeal an administrator's article hide or deletion, and should the action notification include an administrator-provided reason?

Answer: Allow one appeal. The reason behavior is the same: the administrator may provide one, otherwise use the generic message.

Decision: The affected author may submit one appeal against an administrator hide or deletion of their article. The administrator may provide a reason for hide or deletion; include it in the notification when present, otherwise use a generic action message. Reuse the established appeal form limits: up to 200 Chinese characters and three evidence images. An appeal is reviewed once by the administrator; the review result is final. If granted, restore the article to its pre-action state; if rejected, the administrative hide or deletion remains in effect.
Notes: This extends the established moderation appeal capability to administrator article actions without creating a separate evidence format.

### Q312 - Guestbook Comment Control

Question: Who controls guestbook commenting, and may visitors leave anonymous guestbook comments by default?

Answer: The administrator controls it. Visitors may comment anonymously.

Decision: The administrator controls whether the guestbook accepts new comments and whether login is required to post them. By default, guestbook commenting is enabled and visitors may leave anonymous comments. Guestbook comments otherwise inherit the established article-comment rules for buffering, rate limiting, moderation, reporting, deletion, and display.
Notes: This resolves the guestbook's ownership of comment settings.

### Q313 - Derived Guestbook Moderation Ownership

Question: How do article-author comment-management rules apply where the guestbook has no individual article author?

Answer: Resolved from the established ownership model; no new user choice required.

Decision: Treat the guestbook as administrator-owned public content. The administrator receives its deep-thread alerts, manages its comments, and exercises the established direct comment-deletion and moderation permissions. This preserves all inherited guestbook-comment workflows without an unowned moderation path.
Notes: This is a derived ownership rule, not a new public capability.

### Q314 - Configurable Article Body Size Limit

Question: Should the blog impose a per-article body-size limit, independent of uploaded image sizes?

Answer: Enable the limit for now. It excludes image size and may be configured by the administrator.

Decision: Enforce a configurable maximum serialized text-body size for each Markdown or rich-text article, initially set to 2 MB. Do not count images or other separately stored media toward this limit. Expose the limit as an administrator-managed site setting and apply it to both editing and imports.
Notes: The configured value will have an implementation-level safe range to protect database and request processing.

### Q315 - Associated Data After Permanent Article Deletion

Question: Once an article's seven-day deletion cooldown expires, should associated comments and comment images be deleted while moderation records remain?

Answer: Yes.

Decision: On permanent article deletion, permanently remove every associated comment, reply, and comment image together with the article body and article media. Retain related reports, appeals, and audit records for administrative traceability, even though their original comment content no longer exists.
Notes: This resolves final article-deletion data cleanup and moderation-record retention.

### Q316 - Derived Article Rendering Safety

Question: How should established Markdown, rich-text, link, image, and trusted-embed rules be safely rendered?

Answer: Resolved from the existing content-security boundary; no new user choice required.

Decision: Sanitize every Markdown and rich-text rendering path with a shared allowlist. Disallow executable scripts, inline event handlers, unsafe URL schemes, and arbitrary raw HTML execution. Preserve only approved semantic formatting, validated links, validated uploaded images, and the established bilibili trusted embed. Open external links in a separate tab with safe browser isolation attributes.
Notes: This is a mandatory implementation security rule consistent with the existing trusted-embed and external-link policies.

### Q317 - Derived Default Article Comment Access

Question: What should the unconfigured comment-login requirements be for a newly created article?

Answer: Resolved from the established public-default and visitor-comment rules; no new user choice required.

Decision: A newly created article defaults to public visibility, draft status, comments enabled, login not required to view comments, and login not required to publish top-level comments. The author may enable either login requirement during creation or later editing.
Notes: This closes the otherwise unspecified defaults for per-article comment access.

### Q318 - Reconciliation of Global Image Upload Limit

Question: How does the later project-wide image standard affect earlier per-feature image-size decisions?

Answer: Resolved from the later explicit global standard; no new user choice required.

Decision: The later Q164 project-wide maximum of 2 MB overrides every earlier 5 MB image-size allowance, including article covers, inline article images, comment images, avatars, logos, report evidence, imports, and all future image upload surfaces. Preserve each feature's separately specified allowed formats and non-size behavior, such as GIF animation retention and EXIF removal.
Notes: This resolves the historical size-limit conflict in favor of the user's later global rule.

### Q319 - Umami Analytics Coverage

Question: Should Umami track only public pages, or all site areas including authenticated, private, personal, and administrative pages?

Answer: Track all of them.

Decision: Configure self-hosted Umami to collect analytics across all site areas: public pages, authenticated content, private articles, personal pages, and administrator workflows. Analytics remain accessible only to the administrator through the integrated administration interface.
Notes: Analytics data-retention duration remains a material unresolved choice.

### Q320 - Umami Analytics Retention

Question: How long should Umami analytics data be retained before automatic cleanup?

Answer: One month.

Decision: Retain Umami analytics data for one month, then automatically remove expired analytics records.
Notes: This resolves analytics retention and bounds analytics database growth.

### Q321 - Markdown Import into an Existing Rich-Text Article

Question: Given normal article-format immutability, may a Markdown bulk import update an existing rich-text article with the same ID?

Answer: It may update, directly replacing it with the Markdown version.

Decision: Treat bulk Markdown import as an explicit exception to normal per-article format immutability. When an authorized update targets a rich-text article, replace its current content with the imported Markdown version and make Markdown the current content format. Retain the prior rich-text state in version history; historical restoration may restore its original saved format as part of the complete version state.
Notes: This resolves the import and format-immutability conflict.

### Q322 - Derived Initial External-Integration Boundary

Question: What external client and authentication interfaces follow from the confirmed server-rendered initial stack?

Answer: Resolved from the established stack and requested scope; no new user choice required.

Decision: Provide no public API, mobile-app API, or third-party social-login integration in the initial release. Deliver all user and administrator workflows through the same-origin Django-rendered web application, using its internal HTMX endpoints only for browser interactions. Do not expose a reusable external authentication or content API.
Notes: This prevents unrequested expansion of the authentication and authorization surface.
