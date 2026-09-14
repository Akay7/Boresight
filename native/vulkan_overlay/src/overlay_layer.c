/* The Vulkan present-overlay layer.
 *
 * Draws the marker patches `render_overlay` computes into a game's own
 * presented frames by hooking `vkQueuePresentKHR` from inside the
 * game's own process, using the Vulkan loader's explicit-layer
 * mechanism -- the same extension point MangoHud, RenderDoc and the
 * Steam overlay already use. See ../../openspec/changes/
 * add-vulkan-present-overlay/design.md for the full rationale; this
 * file follows its decisions closely:
 *
 *   - vkCreateInstance / vkCreateDevice are intercepted only to walk
 *     the loader's pNext chain for the next layer's GetProcAddr and
 *     build a dispatch table -- their own behaviour is untouched.
 *   - vkCreateSwapchainKHR / vkDestroySwapchainKHR are intercepted to
 *     learn (and free) each swapchain's images, format and extent, and
 *     to upload the marker canvas once as a device-local image.
 *   - vkQueuePresentKHR is the only call whose behaviour actually
 *     changes: it submits a self-contained command buffer that copies
 *     the canvas into each marker rectangle, chained through
 *     semaphores ahead of the real present, and never touches the
 *     application's own command buffers or resources.
 *
 * Deliberately not linked against libvulkan: a Vulkan layer is loaded
 * by the *loader*, which hands it every function pointer it needs
 * through the pNext chain of vkCreateInstance/vkCreateDevice -- linking
 * against libvulkan.so would be pointless (nothing here calls a
 * loader-exported entry point directly) and would make this .so
 * depend on the very loader it is meant to be layered underneath.
 * Only Vulkan-Headers' type/constant definitions are used, not the
 * loader library.
 */

#include <errno.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include <vulkan/vk_layer.h>
#include <vulkan/vulkan.h>

#include "canvas_format.h"

#define VK_LAYER_EXPORT __attribute__((visibility("default")))

/* Every dispatchable Vulkan handle's first word is a pointer to the
 * loader's own dispatch table for that object -- undocumented in the
 * spec proper, but it is the load-bearing assumption the loader/layer
 * interface is built on, and every layer sample uses it exactly this
 * way to key its own per-object state off handles it did not allocate.
 * VkPhysicalDevice and VkQueue share their owning VkInstance/VkDevice's
 * dispatch pointer, which is what lets `find_instance`/`find_device`
 * below work from a VkPhysicalDevice or VkQueue too. */
#define GET_KEY(handle) (*(void **)(handle))

/* ------------------------------------------------------------------ */
/* Per-instance and per-device state                                   */
/* ------------------------------------------------------------------ */

typedef struct swapchain_state {
    VkSwapchainKHR swapchain;
    VkExtent2D extent;
    VkFormat format;

    uint32_t image_count;
    VkImage *images; /* borrowed from the loader, not ours to free */

    /* Whether this layer successfully added VK_IMAGE_USAGE_TRANSFER_DST_BIT
     * to the swapchain's own image usage (see boresight_CreateSwapchainKHR):
     * without it, vkCmdCopyImage into a swapchain image is invalid no
     * matter how correct everything else is -- caught by
     * VK_LAYER_KHRONOS_validation against vkcube, which only requests
     * COLOR_ATTACHMENT usage for its own swapchain. */
    bool transfer_dst_supported;

    bool overlay_ready;

    /* Canvas resources, uploaded once at swapchain creation. */
    VkImage canvas_image;
    VkDeviceMemory canvas_memory;

    /* One pre-recorded command buffer per swapchain image index --
     * static once recorded, since the canvas and rectangles never
     * change for the lifetime of a swapchain (see design.md's "record
     * (or reuse, if geometry hasn't changed)"). */
    VkCommandPool command_pool;
    VkCommandBuffer *command_buffers; /* image_count entries */

    /* One binary semaphore per swapchain image, not one shared across
     * the whole swapchain: a binary semaphore must be unsignaled when
     * signalled again, and with more than one image in flight (the
     * common case -- vkcube's own default is 3), a single shared
     * semaphore gets re-signalled for image N+1 before the present of
     * image N has necessarily been waited on. Caught by
     * VK_LAYER_KHRONOS_validation (VUID-vkQueueSubmit-pSignalSemaphores-00067)
     * stacked underneath during development; indexed by image index,
     * matching `command_buffers` above. */
    VkSemaphore *layer_semaphores; /* image_count entries */

    struct swapchain_state *next;
} swapchain_state_t;

typedef struct instance_data {
    void *key;
    VkInstance instance;
    PFN_vkGetInstanceProcAddr gipa;

    PFN_vkDestroyInstance DestroyInstance;
    PFN_vkGetPhysicalDeviceMemoryProperties GetPhysicalDeviceMemoryProperties;
    PFN_vkGetPhysicalDeviceQueueFamilyProperties GetPhysicalDeviceQueueFamilyProperties;
    PFN_vkGetPhysicalDeviceSurfaceCapabilitiesKHR GetPhysicalDeviceSurfaceCapabilitiesKHR;

    /* Startup diagnostic (spec: "An application that cannot host this
     * backend fails with an actionable diagnostic" / task 4.1): a
     * detached thread that fires once if no swapchain has been created
     * within a short window of instance creation. */
    volatile int swapchain_seen;
    pthread_t timeout_thread;

    struct instance_data *next;
} instance_data_t;

typedef struct device_data {
    void *key;
    VkDevice device;
    VkPhysicalDevice physical_device;
    instance_data_t *instance;
    PFN_vkGetDeviceProcAddr gdpa;

    PFN_vkDestroyDevice DestroyDevice;
    PFN_vkCreateSwapchainKHR CreateSwapchainKHR;
    PFN_vkDestroySwapchainKHR DestroySwapchainKHR;
    PFN_vkGetSwapchainImagesKHR GetSwapchainImagesKHR;
    PFN_vkQueuePresentKHR QueuePresentKHR;
    PFN_vkCreateImage CreateImage;
    PFN_vkDestroyImage DestroyImage;
    PFN_vkGetImageMemoryRequirements GetImageMemoryRequirements;
    PFN_vkAllocateMemory AllocateMemory;
    PFN_vkFreeMemory FreeMemory;
    PFN_vkBindImageMemory BindImageMemory;
    PFN_vkMapMemory MapMemory;
    PFN_vkUnmapMemory UnmapMemory;
    PFN_vkCreateBuffer CreateBuffer;
    PFN_vkDestroyBuffer DestroyBuffer;
    PFN_vkGetBufferMemoryRequirements GetBufferMemoryRequirements;
    PFN_vkBindBufferMemory BindBufferMemory;
    PFN_vkCreateCommandPool CreateCommandPool;
    PFN_vkDestroyCommandPool DestroyCommandPool;
    PFN_vkAllocateCommandBuffers AllocateCommandBuffers;
    PFN_vkBeginCommandBuffer BeginCommandBuffer;
    PFN_vkEndCommandBuffer EndCommandBuffer;
    PFN_vkCmdPipelineBarrier CmdPipelineBarrier;
    PFN_vkCmdCopyImage CmdCopyImage;
    PFN_vkQueueSubmit QueueSubmit;
    PFN_vkQueueWaitIdle QueueWaitIdle;
    PFN_vkCreateSemaphore CreateSemaphore;
    PFN_vkDestroySemaphore DestroySemaphore;
    PFN_vkGetDeviceQueue GetDeviceQueue;
    PFN_vkDeviceWaitIdle DeviceWaitIdle;

    VkQueue present_queue;
    uint32_t queue_family_index;
    bool queue_supports_transfer;

    /* The loader stamps a dispatch pointer into every dispatchable
     * handle *it* hands back to an application, but a handle this
     * layer allocates on its own behalf (the command buffers below)
     * only goes through our "next" chain, skipping that step -- so we
     * must stamp it ourselves, via the callback the loader passes down
     * for exactly this purpose. Omitting this is invisible with no
     * other layer active (the ICD accepts the handle regardless) and
     * crashes the instant a layer that actually keys off the dispatch
     * pointer -- such as VK_LAYER_KHRONOS_validation -- is stacked
     * underneath: found and fixed via that exact stacking. */
    PFN_vkSetDeviceLoaderData set_loader_data;

    pthread_mutex_t lock;
    swapchain_state_t *swapchains;

    struct device_data *next;
} device_data_t;

static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static instance_data_t *g_instances = NULL;
static device_data_t *g_devices = NULL;

static void log_line(const char *fmt, ...) {
    va_list args;
    va_start(args, fmt);
    fprintf(stderr, "boresight-overlay: ");
    vfprintf(stderr, fmt, args);
    fprintf(stderr, "\n");
    va_end(args);
}

/* ------------------------------------------------------------------ */
/* Instance / device bookkeeping                                       */
/* ------------------------------------------------------------------ */

static void add_instance(instance_data_t *data) {
    pthread_mutex_lock(&g_lock);
    data->next = g_instances;
    g_instances = data;
    pthread_mutex_unlock(&g_lock);
}

static instance_data_t *find_instance(void *key) {
    pthread_mutex_lock(&g_lock);
    instance_data_t *data = g_instances;
    while (data && data->key != key) {
        data = data->next;
    }
    pthread_mutex_unlock(&g_lock);
    return data;
}

static instance_data_t *remove_instance(void *key) {
    pthread_mutex_lock(&g_lock);
    instance_data_t **cursor = &g_instances;
    while (*cursor && (*cursor)->key != key) {
        cursor = &(*cursor)->next;
    }
    instance_data_t *found = *cursor;
    if (found) {
        *cursor = found->next;
    }
    pthread_mutex_unlock(&g_lock);
    return found;
}

static void add_device(device_data_t *data) {
    pthread_mutex_lock(&g_lock);
    data->next = g_devices;
    g_devices = data;
    pthread_mutex_unlock(&g_lock);
}

static device_data_t *find_device(void *key) {
    pthread_mutex_lock(&g_lock);
    device_data_t *data = g_devices;
    while (data && data->key != key) {
        data = data->next;
    }
    pthread_mutex_unlock(&g_lock);
    return data;
}

static device_data_t *remove_device(void *key) {
    pthread_mutex_lock(&g_lock);
    device_data_t **cursor = &g_devices;
    while (*cursor && (*cursor)->key != key) {
        cursor = &(*cursor)->next;
    }
    device_data_t *found = *cursor;
    if (found) {
        *cursor = found->next;
    }
    pthread_mutex_unlock(&g_lock);
    return found;
}

static void add_swapchain(device_data_t *dd, swapchain_state_t *sc) {
    pthread_mutex_lock(&dd->lock);
    sc->next = dd->swapchains;
    dd->swapchains = sc;
    pthread_mutex_unlock(&dd->lock);
}

static swapchain_state_t *find_swapchain(device_data_t *dd, VkSwapchainKHR handle) {
    pthread_mutex_lock(&dd->lock);
    swapchain_state_t *sc = dd->swapchains;
    while (sc && sc->swapchain != handle) {
        sc = sc->next;
    }
    pthread_mutex_unlock(&dd->lock);
    return sc;
}

static swapchain_state_t *remove_swapchain(device_data_t *dd, VkSwapchainKHR handle) {
    pthread_mutex_lock(&dd->lock);
    swapchain_state_t **cursor = &dd->swapchains;
    while (*cursor && (*cursor)->swapchain != handle) {
        cursor = &(*cursor)->next;
    }
    swapchain_state_t *found = *cursor;
    if (found) {
        *cursor = found->next;
    }
    pthread_mutex_unlock(&dd->lock);
    return found;
}

/* ------------------------------------------------------------------ */
/* pNext chain walking (the standard loader/layer bootstrap dance)     */
/* ------------------------------------------------------------------ */

static VkLayerInstanceCreateInfo *get_instance_chain_info(
    const VkInstanceCreateInfo *create_info, VkLayerFunction func
) {
    VkLayerInstanceCreateInfo *chain = (VkLayerInstanceCreateInfo *)create_info->pNext;
    while (chain &&
           !(chain->sType == VK_STRUCTURE_TYPE_LOADER_INSTANCE_CREATE_INFO &&
             chain->function == func)) {
        chain = (VkLayerInstanceCreateInfo *)chain->pNext;
    }
    return chain;
}

static VkLayerDeviceCreateInfo *get_device_chain_info(
    const VkDeviceCreateInfo *create_info, VkLayerFunction func
) {
    VkLayerDeviceCreateInfo *chain = (VkLayerDeviceCreateInfo *)create_info->pNext;
    while (chain &&
           !(chain->sType == VK_STRUCTURE_TYPE_LOADER_DEVICE_CREATE_INFO &&
             chain->function == func)) {
        chain = (VkLayerDeviceCreateInfo *)chain->pNext;
    }
    return chain;
}

/* ------------------------------------------------------------------ */
/* Startup diagnostic (spec: "actionable diagnostic" / task 4.1)       */
/* ------------------------------------------------------------------ */

static void *startup_timeout_thread(void *arg) {
    instance_data_t *data = (instance_data_t *)arg;

    long timeout_ms = 5000;
    const char *env = getenv("BORESIGHT_OVERLAY_STARTUP_TIMEOUT_MS");
    if (env && *env) {
        char *end = NULL;
        long parsed = strtol(env, &end, 10);
        if (end != env && parsed > 0) {
            timeout_ms = parsed;
        }
    }

    struct timespec ts = {
        .tv_sec = timeout_ms / 1000,
        .tv_nsec = (timeout_ms % 1000) * 1000000L,
    };
    nanosleep(&ts, NULL);

    if (!data->swapchain_seen) {
        log_line(
            "this application has not presented a Vulkan swapchain %ldms "
            "after startup. Either it does not present through Vulkan "
            "(for example, wined3d's OpenGL path) or it has not reached "
            "its render loop yet. The window-based overlay "
            "(`python -m boresight.overlay`) or printed markers "
            "(open /markers) work regardless of the presentation API.",
            timeout_ms
        );
    }
    return NULL;
}

/* ------------------------------------------------------------------ */
/* Canvas upload and command-buffer recording                          */
/* ------------------------------------------------------------------ */

/* Formats this layer knows how to copy into: every 4-byte-per-texel
 * swapchain format actually observed in practice -- the 8-bit-per-
 * channel UNORM/SRGB families DXVK and VKD3D-Proton negotiate, and the
 * packed 10-bit families some Wayland compositors hand back instead
 * (confirmed against this machine's own KDE/RADV session, which
 * negotiates VK_FORMAT_A2R10G10B10_UNORM_PACK32 for vkcube).
 * `vkCmdCopyImage` requires identical texel size between images with no
 * format conversion (see design.md: "pure transfer, no graphics
 * pipeline"), so the canvas image is created in the *same* format as
 * the swapchain and the uploaded pixel data is expanded to match --
 * rather than attempting a scaling blit, which design.md explicitly
 * ruled out. A swapchain in some other format is a case this layer
 * skips drawing for (log once, pass every present through unmodified)
 * rather than one it guesses at. */
static bool format_is_supported(VkFormat format) {
    switch (format) {
        case VK_FORMAT_B8G8R8A8_UNORM:
        case VK_FORMAT_B8G8R8A8_SRGB:
        case VK_FORMAT_R8G8B8A8_UNORM:
        case VK_FORMAT_R8G8B8A8_SRGB:
        case VK_FORMAT_A2R10G10B10_UNORM_PACK32:
        case VK_FORMAT_A2B10G10R10_UNORM_PACK32:
            return true;
        default:
            return false;
    }
}

/* Writes one texel of `format` at `dst` (always 4 bytes here) for a
 * grayscale sample `gray` -- every marker patch is monochrome, so
 * every channel of a multi-channel format gets the same value and
 * which channel is which never matters, only how many bits it gets. */
static void write_texel(uint8_t *dst, VkFormat format, uint8_t gray) {
    switch (format) {
        case VK_FORMAT_A2R10G10B10_UNORM_PACK32:
        case VK_FORMAT_A2B10G10R10_UNORM_PACK32: {
            uint32_t v10 = ((uint32_t)gray * 1023u + 127u) / 255u;
            uint32_t word = (3u << 30) | (v10 << 20) | (v10 << 10) | v10;
            memcpy(dst, &word, sizeof(word));
            break;
        }
        default:
            dst[0] = gray;
            dst[1] = gray;
            dst[2] = gray;
            dst[3] = 255;
            break;
    }
}

static bool find_memory_type(
    const VkPhysicalDeviceMemoryProperties *props,
    uint32_t type_bits,
    VkMemoryPropertyFlags required,
    uint32_t *out
) {
    for (uint32_t i = 0; i < props->memoryTypeCount; i++) {
        if ((type_bits & (1u << i)) &&
            (props->memoryTypes[i].propertyFlags & required) == required) {
            *out = i;
            return true;
        }
    }
    return false;
}

/* Reads BORESIGHT_OVERLAY_CANVAS, checks it against `sc`'s extent and
 * format, uploads it as a device-local image, and pre-records one
 * command buffer per swapchain image that blits the canvas into every
 * marker rectangle. Returns false (leaving `sc` untouched beyond
 * whatever partial state it cleans up itself) for every case this
 * backend cannot draw into -- no canvas configured, format/extent
 * mismatch, an unsupported queue -- so the caller's fallback is always
 * "pass this present straight through," never a failed frame. */
static bool try_setup_overlay(device_data_t *dd, swapchain_state_t *sc) {
    const char *canvas_path = getenv("BORESIGHT_OVERLAY_CANVAS");
    if (!canvas_path || !*canvas_path) {
        /* Not opted in for this launch -- the common case for any
         * Vulkan application on a system where this layer happens to
         * be built, and exactly the "enabled explicitly, per
         * application" requirement. */
        return false;
    }

    if (!sc->transfer_dst_supported) {
        log_line(
            "this swapchain's surface does not support "
            "VK_IMAGE_USAGE_TRANSFER_DST_BIT, so this layer cannot copy "
            "into its images; the window overlay or printed markers "
            "still work."
        );
        return false;
    }

    if (!dd->set_loader_data) {
        /* Every loader implementing interface v2+ provides this, so
         * finding none would mean an unexpectedly old or non-compliant
         * loader -- refuse to draw rather than hand out command
         * buffers no other layer can safely dispatch through. */
        log_line(
            "this Vulkan loader did not provide a device loader-data "
            "callback; cannot safely allocate command buffers, so this "
            "layer will not draw. The window overlay or printed markers "
            "still work."
        );
        return false;
    }

    if (!dd->queue_supports_transfer) {
        log_line(
            "the device queue this application created does not report "
            "graphics or compute support, so this layer cannot copy into "
            "its swapchain images; the window overlay or printed markers "
            "still work."
        );
        return false;
    }

    if (!format_is_supported(sc->format)) {
        log_line(
            "swapchain format %d is not one this layer knows how to copy "
            "into (supported: B/R8G8B8A8 UNORM/SRGB); skipping the "
            "overlay for this swapchain.",
            (int)sc->format
        );
        return false;
    }

    bsov_canvas_t canvas = {0};
    if (bsov_load(canvas_path, &canvas) != 0) {
        log_line(
            "could not read a valid marker canvas from '%s'; skipping the "
            "overlay for this swapchain.",
            canvas_path
        );
        return false;
    }

    if (canvas.width != sc->extent.width || canvas.height != sc->extent.height) {
        log_line(
            "the marker canvas was generated for %ux%u but this swapchain "
            "presents at %ux%u; skipping the overlay for this swapchain "
            "rather than drawing a stale layout. Relaunch after a "
            "resolution change so the canvas is regenerated for the new "
            "size.",
            canvas.width, canvas.height, sc->extent.width, sc->extent.height
        );
        bsov_free(&canvas);
        return false;
    }

    VkPhysicalDeviceMemoryProperties mem_props;
    dd->instance->GetPhysicalDeviceMemoryProperties(dd->physical_device, &mem_props);

    bool ok = true;
    VkBuffer staging_buffer = VK_NULL_HANDLE;
    VkDeviceMemory staging_memory = VK_NULL_HANDLE;
    VkCommandPool pool = VK_NULL_HANDLE;
    VkCommandBuffer setup_cmd = VK_NULL_HANDLE;

    /* --- Expand grayscale -> the swapchain's 4-byte-per-texel format. --- */
    size_t pixel_count = (size_t)canvas.width * (size_t)canvas.height;
    uint8_t *rgba = malloc(pixel_count * 4);
    if (!rgba) {
        bsov_free(&canvas);
        return false;
    }
    for (size_t i = 0; i < pixel_count; i++) {
        write_texel(&rgba[i * 4], sc->format, canvas.pixels[i]);
    }
    VkDeviceSize buffer_size = (VkDeviceSize)pixel_count * 4;

    /* --- Staging buffer --- */
    VkBufferCreateInfo buffer_info = {
        .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .size = buffer_size,
        .usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT,
        .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
    };
    if (dd->CreateBuffer(dd->device, &buffer_info, NULL, &staging_buffer) != VK_SUCCESS) {
        ok = false;
        goto cleanup;
    }
    VkMemoryRequirements buffer_reqs;
    dd->GetBufferMemoryRequirements(dd->device, staging_buffer, &buffer_reqs);
    uint32_t staging_type = 0;
    if (!find_memory_type(
            &mem_props, buffer_reqs.memoryTypeBits,
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT,
            &staging_type
        )) {
        ok = false;
        goto cleanup;
    }
    VkMemoryAllocateInfo staging_alloc = {
        .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .allocationSize = buffer_reqs.size,
        .memoryTypeIndex = staging_type,
    };
    if (dd->AllocateMemory(dd->device, &staging_alloc, NULL, &staging_memory) != VK_SUCCESS) {
        ok = false;
        goto cleanup;
    }
    dd->BindBufferMemory(dd->device, staging_buffer, staging_memory, 0);

    void *mapped = NULL;
    if (dd->MapMemory(dd->device, staging_memory, 0, buffer_size, 0, &mapped) != VK_SUCCESS) {
        ok = false;
        goto cleanup;
    }
    memcpy(mapped, rgba, buffer_size);
    dd->UnmapMemory(dd->device, staging_memory);

    /* --- Device-local canvas image, same format as the swapchain --- */
    VkImageCreateInfo image_info = {
        .sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
        .imageType = VK_IMAGE_TYPE_2D,
        .format = sc->format,
        .extent = {canvas.width, canvas.height, 1},
        .mipLevels = 1,
        .arrayLayers = 1,
        .samples = VK_SAMPLE_COUNT_1_BIT,
        .tiling = VK_IMAGE_TILING_OPTIMAL,
        .usage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT,
        .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
        .initialLayout = VK_IMAGE_LAYOUT_UNDEFINED,
    };
    if (dd->CreateImage(dd->device, &image_info, NULL, &sc->canvas_image) != VK_SUCCESS) {
        ok = false;
        goto cleanup;
    }
    VkMemoryRequirements image_reqs;
    dd->GetImageMemoryRequirements(dd->device, sc->canvas_image, &image_reqs);
    uint32_t image_type = 0;
    if (!find_memory_type(
            &mem_props, image_reqs.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT,
            &image_type
        )) {
        ok = false;
        goto cleanup;
    }
    VkMemoryAllocateInfo image_alloc = {
        .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .allocationSize = image_reqs.size,
        .memoryTypeIndex = image_type,
    };
    if (dd->AllocateMemory(dd->device, &image_alloc, NULL, &sc->canvas_memory) != VK_SUCCESS) {
        ok = false;
        goto cleanup;
    }
    dd->BindImageMemory(dd->device, sc->canvas_image, sc->canvas_memory, 0);

    /* --- Command pool: one setup buffer (upload) plus one present-hook
     * buffer per swapchain image, all from the same pool. --- */
    VkCommandPoolCreateInfo pool_info = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
        .flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT,
        .queueFamilyIndex = dd->queue_family_index,
    };
    if (dd->CreateCommandPool(dd->device, &pool_info, NULL, &pool) != VK_SUCCESS) {
        ok = false;
        goto cleanup;
    }

    VkCommandBufferAllocateInfo setup_alloc = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
        .commandPool = pool,
        .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
        .commandBufferCount = 1,
    };
    if (dd->AllocateCommandBuffers(dd->device, &setup_alloc, &setup_cmd) != VK_SUCCESS) {
        ok = false;
        goto cleanup;
    }
    dd->set_loader_data(dd->device, setup_cmd);

    VkCommandBufferBeginInfo begin_info = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
    };
    dd->BeginCommandBuffer(setup_cmd, &begin_info);

    VkImageMemoryBarrier to_transfer_dst = {
        .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
        .srcAccessMask = 0,
        .dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT,
        .oldLayout = VK_IMAGE_LAYOUT_UNDEFINED,
        .newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
        .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .image = sc->canvas_image,
        .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1},
    };
    dd->CmdPipelineBarrier(
        setup_cmd, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0,
        NULL, 0, NULL, 1, &to_transfer_dst
    );

    VkBufferImageCopy copy_region = {
        .bufferOffset = 0,
        .bufferRowLength = 0,
        .bufferImageHeight = 0,
        .imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
        .imageOffset = {0, 0, 0},
        .imageExtent = {canvas.width, canvas.height, 1},
    };
    PFN_vkCmdCopyBufferToImage CmdCopyBufferToImage =
        (PFN_vkCmdCopyBufferToImage)dd->gdpa(dd->device, "vkCmdCopyBufferToImage");
    CmdCopyBufferToImage(
        setup_cmd, staging_buffer, sc->canvas_image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1,
        &copy_region
    );

    VkImageMemoryBarrier to_transfer_src = to_transfer_dst;
    to_transfer_src.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    to_transfer_src.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    to_transfer_src.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
    to_transfer_src.newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
    dd->CmdPipelineBarrier(
        setup_cmd, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0,
        NULL, 1, &to_transfer_src
    );

    dd->EndCommandBuffer(setup_cmd);

    VkSubmitInfo setup_submit = {
        .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
        .commandBufferCount = 1,
        .pCommandBuffers = &setup_cmd,
    };
    dd->QueueSubmit(dd->present_queue, 1, &setup_submit, VK_NULL_HANDLE);
    dd->QueueWaitIdle(dd->present_queue);
    /* One-time cost at swapchain creation, never per frame -- waiting
     * here rather than juggling a fence is the simpler correct choice
     * for something that happens once. */

    /* --- Per-image present-hook command buffers, recorded once --- */
    sc->command_buffers = calloc(sc->image_count, sizeof(VkCommandBuffer));
    if (!sc->command_buffers) {
        ok = false;
        goto cleanup;
    }
    VkCommandBufferAllocateInfo present_alloc = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
        .commandPool = pool,
        .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
        .commandBufferCount = sc->image_count,
    };
    if (dd->AllocateCommandBuffers(dd->device, &present_alloc, sc->command_buffers) !=
        VK_SUCCESS) {
        ok = false;
        goto cleanup;
    }
    for (uint32_t i = 0; i < sc->image_count; i++) {
        dd->set_loader_data(dd->device, sc->command_buffers[i]);
    }

    for (uint32_t i = 0; i < sc->image_count; i++) {
        VkCommandBuffer cmd = sc->command_buffers[i];
        VkCommandBufferBeginInfo present_begin = {
            .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
            .flags = VK_COMMAND_BUFFER_USAGE_SIMULTANEOUS_USE_BIT,
        };
        dd->BeginCommandBuffer(cmd, &present_begin);

        /* The application already transitioned this image to
         * PRESENT_SRC_KHR before calling vkQueuePresentKHR -- that is
         * the documented swapchain usage contract every frame, not
         * just the first -- so it is always the correct starting
         * layout for this pre-recorded sequence. */
        VkImageMemoryBarrier swap_to_dst = {
            .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
            .srcAccessMask = 0,
            .dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT,
            .oldLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR,
            .newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
            .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .image = sc->images[i],
            .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1},
        };
        dd->CmdPipelineBarrier(
            cmd, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL,
            0, NULL, 1, &swap_to_dst
        );

        for (uint32_t r = 0; r < canvas.rect_count; r++) {
            bsov_rect_t rect = canvas.rects[r];
            VkImageCopy region = {
                .srcSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
                .srcOffset = {(int32_t)rect.x, (int32_t)rect.y, 0},
                .dstSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
                .dstOffset = {(int32_t)rect.x, (int32_t)rect.y, 0},
                .extent = {rect.w, rect.h, 1},
            };
            dd->CmdCopyImage(
                cmd, sc->canvas_image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, sc->images[i],
                VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &region
            );
        }

        VkImageMemoryBarrier swap_to_present = swap_to_dst;
        swap_to_present.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        swap_to_present.dstAccessMask = 0;
        swap_to_present.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
        swap_to_present.newLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
        dd->CmdPipelineBarrier(
            cmd, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, 0, 0, NULL,
            0, NULL, 1, &swap_to_present
        );

        dd->EndCommandBuffer(cmd);
    }

    VkSemaphoreCreateInfo semaphore_info = {.sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO};
    sc->layer_semaphores = calloc(sc->image_count, sizeof(VkSemaphore));
    if (!sc->layer_semaphores) {
        ok = false;
        goto cleanup;
    }
    for (uint32_t i = 0; i < sc->image_count; i++) {
        if (dd->CreateSemaphore(dd->device, &semaphore_info, NULL, &sc->layer_semaphores[i]) !=
            VK_SUCCESS) {
            ok = false;
            goto cleanup;
        }
    }

    sc->command_pool = pool;
    pool = VK_NULL_HANDLE; /* ownership moved to sc; do not destroy below */

cleanup:
    /* `pool` is only still non-NULL here on a path that failed before
     * ownership transferred to `sc` (the success path sets it back to
     * VK_NULL_HANDLE below), so destroying it is always correct -- it
     * also frees `setup_cmd` and any present-hook buffers already
     * allocated from it. */
    if (pool != VK_NULL_HANDLE) {
        dd->DestroyCommandPool(dd->device, pool, NULL);
    }
    if (staging_buffer != VK_NULL_HANDLE) {
        dd->DestroyBuffer(dd->device, staging_buffer, NULL);
    }
    if (staging_memory != VK_NULL_HANDLE) {
        dd->FreeMemory(dd->device, staging_memory, NULL);
    }
    free(rgba);
    bsov_free(&canvas);

    if (!ok) {
        if (sc->canvas_image != VK_NULL_HANDLE) {
            dd->DestroyImage(dd->device, sc->canvas_image, NULL);
            sc->canvas_image = VK_NULL_HANDLE;
        }
        if (sc->canvas_memory != VK_NULL_HANDLE) {
            dd->FreeMemory(dd->device, sc->canvas_memory, NULL);
            sc->canvas_memory = VK_NULL_HANDLE;
        }
        free(sc->command_buffers);
        sc->command_buffers = NULL;
        if (sc->layer_semaphores) {
            for (uint32_t i = 0; i < sc->image_count; i++) {
                if (sc->layer_semaphores[i] != VK_NULL_HANDLE) {
                    dd->DestroySemaphore(dd->device, sc->layer_semaphores[i], NULL);
                }
            }
            free(sc->layer_semaphores);
            sc->layer_semaphores = NULL;
        }
        log_line("could not set up the overlay for this swapchain; drawing nothing on it.");
    }
    return ok;
}

static void teardown_overlay(device_data_t *dd, swapchain_state_t *sc) {
    if (sc->layer_semaphores) {
        for (uint32_t i = 0; i < sc->image_count; i++) {
            if (sc->layer_semaphores[i] != VK_NULL_HANDLE) {
                dd->DestroySemaphore(dd->device, sc->layer_semaphores[i], NULL);
            }
        }
        free(sc->layer_semaphores);
    }
    if (sc->command_pool != VK_NULL_HANDLE) {
        dd->DestroyCommandPool(dd->device, sc->command_pool, NULL);
    }
    if (sc->canvas_image != VK_NULL_HANDLE) {
        dd->DestroyImage(dd->device, sc->canvas_image, NULL);
    }
    if (sc->canvas_memory != VK_NULL_HANDLE) {
        dd->FreeMemory(dd->device, sc->canvas_memory, NULL);
    }
    free(sc->command_buffers);
    free(sc->images);
}

/* ------------------------------------------------------------------ */
/* Intercepted entry points                                            */
/* ------------------------------------------------------------------ */

static VkResult VKAPI_CALL boresight_CreateInstance(
    const VkInstanceCreateInfo *create_info, const VkAllocationCallbacks *allocator,
    VkInstance *instance
) {
    VkLayerInstanceCreateInfo *chain_info =
        get_instance_chain_info(create_info, VK_LAYER_LINK_INFO);
    if (!chain_info) {
        return VK_ERROR_INITIALIZATION_FAILED;
    }

    PFN_vkGetInstanceProcAddr next_gipa = chain_info->u.pLayerInfo->pfnNextGetInstanceProcAddr;
    PFN_vkCreateInstance create_next =
        (PFN_vkCreateInstance)next_gipa(NULL, "vkCreateInstance");
    if (!create_next) {
        return VK_ERROR_INITIALIZATION_FAILED;
    }

    chain_info->u.pLayerInfo = chain_info->u.pLayerInfo->pNext;
    VkResult result = create_next(create_info, allocator, instance);
    if (result != VK_SUCCESS) {
        return result;
    }

    instance_data_t *data = calloc(1, sizeof(*data));
    data->key = GET_KEY(*instance);
    data->instance = *instance;
    data->gipa = next_gipa;
    data->DestroyInstance = (PFN_vkDestroyInstance)next_gipa(*instance, "vkDestroyInstance");
    data->GetPhysicalDeviceMemoryProperties = (PFN_vkGetPhysicalDeviceMemoryProperties)next_gipa(
        *instance, "vkGetPhysicalDeviceMemoryProperties"
    );
    data->GetPhysicalDeviceQueueFamilyProperties =
        (PFN_vkGetPhysicalDeviceQueueFamilyProperties)next_gipa(
            *instance, "vkGetPhysicalDeviceQueueFamilyProperties"
        );
    data->GetPhysicalDeviceSurfaceCapabilitiesKHR =
        (PFN_vkGetPhysicalDeviceSurfaceCapabilitiesKHR)next_gipa(
            *instance, "vkGetPhysicalDeviceSurfaceCapabilitiesKHR"
        );
    data->swapchain_seen = 0;

    log_line("layer loaded (VkInstance %p)", (void *)*instance);

    add_instance(data);
    pthread_create(&data->timeout_thread, NULL, startup_timeout_thread, data);
    pthread_detach(data->timeout_thread);

    return VK_SUCCESS;
}

static void VKAPI_CALL boresight_DestroyInstance(
    VkInstance instance, const VkAllocationCallbacks *allocator
) {
    instance_data_t *data = remove_instance(GET_KEY(instance));
    PFN_vkDestroyInstance destroy_next = data ? data->DestroyInstance : NULL;
    free(data);
    if (destroy_next) {
        destroy_next(instance, allocator);
    }
}

static VkResult VKAPI_CALL boresight_CreateDevice(
    VkPhysicalDevice physical_device, const VkDeviceCreateInfo *create_info,
    const VkAllocationCallbacks *allocator, VkDevice *device
) {
    VkLayerDeviceCreateInfo *chain_info = get_device_chain_info(create_info, VK_LAYER_LINK_INFO);
    if (!chain_info) {
        return VK_ERROR_INITIALIZATION_FAILED;
    }
    VkLayerDeviceCreateInfo *loader_data_info =
        get_device_chain_info(create_info, VK_LOADER_DATA_CALLBACK);

    PFN_vkGetInstanceProcAddr next_gipa = chain_info->u.pLayerInfo->pfnNextGetInstanceProcAddr;
    PFN_vkGetDeviceProcAddr next_gdpa = chain_info->u.pLayerInfo->pfnNextGetDeviceProcAddr;
    PFN_vkCreateDevice create_next = (PFN_vkCreateDevice)next_gipa(NULL, "vkCreateDevice");
    if (!create_next) {
        return VK_ERROR_INITIALIZATION_FAILED;
    }

    chain_info->u.pLayerInfo = chain_info->u.pLayerInfo->pNext;
    VkResult result = create_next(physical_device, create_info, allocator, device);
    if (result != VK_SUCCESS) {
        return result;
    }

    device_data_t *dd = calloc(1, sizeof(*dd));
    dd->key = GET_KEY(*device);
    dd->device = *device;
    dd->physical_device = physical_device;
    dd->instance = find_instance(GET_KEY(physical_device));
    dd->gdpa = next_gdpa;
    dd->set_loader_data = loader_data_info ? loader_data_info->u.pfnSetDeviceLoaderData : NULL;
    pthread_mutex_init(&dd->lock, NULL);

#define LOAD(name) dd->name = (PFN_vk##name)next_gdpa(*device, "vk" #name)
    LOAD(DestroyDevice);
    LOAD(CreateSwapchainKHR);
    LOAD(DestroySwapchainKHR);
    LOAD(GetSwapchainImagesKHR);
    LOAD(QueuePresentKHR);
    LOAD(CreateImage);
    LOAD(DestroyImage);
    LOAD(GetImageMemoryRequirements);
    LOAD(AllocateMemory);
    LOAD(FreeMemory);
    LOAD(BindImageMemory);
    LOAD(MapMemory);
    LOAD(UnmapMemory);
    LOAD(CreateBuffer);
    LOAD(DestroyBuffer);
    LOAD(GetBufferMemoryRequirements);
    LOAD(BindBufferMemory);
    LOAD(CreateCommandPool);
    LOAD(DestroyCommandPool);
    LOAD(AllocateCommandBuffers);
    LOAD(BeginCommandBuffer);
    LOAD(EndCommandBuffer);
    LOAD(CmdPipelineBarrier);
    LOAD(CmdCopyImage);
    LOAD(QueueSubmit);
    LOAD(QueueWaitIdle);
    LOAD(CreateSemaphore);
    LOAD(DestroySemaphore);
    LOAD(GetDeviceQueue);
    LOAD(DeviceWaitIdle);
#undef LOAD

    /* A queue family requested by the application is the only one this
     * layer can safely use -- it never creates its own. Index 0 of
     * pQueueCreateInfos is guaranteed to exist and to have been
     * requested with at least one queue; that covers vkcube and the
     * common single-queue-family case DXVK/VKD3D-Proton titles use. A
     * title relying on a queue family that turns out not to support
     * graphics or compute (and therefore transfer -- required
     * implicitly by either, per spec) degrades to drawing nothing
     * rather than guessing at another family the application did not
     * ask for. */
    dd->queue_family_index = create_info->pQueueCreateInfos[0].queueFamilyIndex;
    dd->GetDeviceQueue(*device, dd->queue_family_index, 0, &dd->present_queue);

    uint32_t family_count = 0;
    dd->instance->GetPhysicalDeviceQueueFamilyProperties(physical_device, &family_count, NULL);
    VkQueueFamilyProperties *families = calloc(family_count, sizeof(VkQueueFamilyProperties));
    dd->instance->GetPhysicalDeviceQueueFamilyProperties(physical_device, &family_count, families);
    if (dd->queue_family_index < family_count) {
        VkQueueFlags flags = families[dd->queue_family_index].queueFlags;
        dd->queue_supports_transfer =
            (flags & (VK_QUEUE_GRAPHICS_BIT | VK_QUEUE_COMPUTE_BIT)) != 0;
    }
    free(families);

    add_device(dd);
    return VK_SUCCESS;
}

static void VKAPI_CALL boresight_DestroyDevice(
    VkDevice device, const VkAllocationCallbacks *allocator
) {
    device_data_t *dd = remove_device(GET_KEY(device));
    PFN_vkDestroyDevice destroy_next = dd ? dd->DestroyDevice : NULL;
    if (dd) {
        pthread_mutex_destroy(&dd->lock);
        free(dd);
    }
    if (destroy_next) {
        destroy_next(device, allocator);
    }
}

static VkResult VKAPI_CALL boresight_CreateSwapchainKHR(
    VkDevice device, const VkSwapchainCreateInfoKHR *create_info,
    const VkAllocationCallbacks *allocator, VkSwapchainKHR *swapchain
) {
    device_data_t *dd = find_device(GET_KEY(device));
    if (!dd) {
        return VK_ERROR_DEVICE_LOST;
    }

    /* The application's own imageUsage is whatever *it* needs (vkcube,
     * and plenty of real titles, request only COLOR_ATTACHMENT) --
     * vkCmdCopyImage into a swapchain image additionally needs
     * TRANSFER_DST on that image, which only the application's own
     * vkCreateSwapchainKHR call can grant. Adding the bit here, when
     * the surface reports it as supported, is the standard technique
     * (the same one MangoHud and similar layers use) and is purely
     * additive: it changes nothing about how the application itself
     * uses the image, only what else becomes legal to do to it. */
    VkSwapchainCreateInfoKHR modified_create_info = *create_info;
    bool transfer_dst_supported = false;
    if (dd->instance->GetPhysicalDeviceSurfaceCapabilitiesKHR) {
        VkSurfaceCapabilitiesKHR capabilities;
        if (dd->instance->GetPhysicalDeviceSurfaceCapabilitiesKHR(
                dd->physical_device, create_info->surface, &capabilities
            ) == VK_SUCCESS &&
            (capabilities.supportedUsageFlags & VK_IMAGE_USAGE_TRANSFER_DST_BIT)) {
            modified_create_info.imageUsage |= VK_IMAGE_USAGE_TRANSFER_DST_BIT;
            transfer_dst_supported = true;
        }
    }

    VkResult result =
        dd->CreateSwapchainKHR(device, &modified_create_info, allocator, swapchain);
    if (result != VK_SUCCESS) {
        return result;
    }

    dd->instance->swapchain_seen = 1;

    swapchain_state_t *sc = calloc(1, sizeof(*sc));
    sc->swapchain = *swapchain;
    sc->extent = create_info->imageExtent;
    sc->format = create_info->imageFormat;
    sc->transfer_dst_supported = transfer_dst_supported;

    dd->GetSwapchainImagesKHR(device, *swapchain, &sc->image_count, NULL);
    sc->images = calloc(sc->image_count, sizeof(VkImage));
    dd->GetSwapchainImagesKHR(device, *swapchain, &sc->image_count, sc->images);

    sc->overlay_ready = try_setup_overlay(dd, sc);

    add_swapchain(dd, sc);
    return VK_SUCCESS;
}

static void VKAPI_CALL boresight_DestroySwapchainKHR(
    VkDevice device, VkSwapchainKHR swapchain, const VkAllocationCallbacks *allocator
) {
    device_data_t *dd = find_device(GET_KEY(device));
    if (dd) {
        swapchain_state_t *sc = remove_swapchain(dd, swapchain);
        if (sc) {
            dd->DeviceWaitIdle(device);
            teardown_overlay(dd, sc);
            free(sc);
        }
        dd->DestroySwapchainKHR(device, swapchain, allocator);
        return;
    }
    /* Should not happen -- a swapchain always belongs to a device this
     * layer saw created -- but never crash on a lookup miss. */
}

#define MAX_SWAPCHAINS_PER_PRESENT 8
#define MAX_WAIT_SEMAPHORES 16

static VkResult VKAPI_CALL boresight_QueuePresentKHR(
    VkQueue queue, const VkPresentInfoKHR *present_info
) {
    device_data_t *dd = find_device(GET_KEY(queue));
    if (!dd) {
        /* Cannot even find our own dispatch table for this queue --
         * refuse to guess, but there is also no "next" function to
         * call through to. This should be unreachable in practice. */
        return VK_ERROR_DEVICE_LOST;
    }

    uint32_t n = present_info->swapchainCount;
    bool all_ready = n <= MAX_SWAPCHAINS_PER_PRESENT &&
                      present_info->waitSemaphoreCount <= MAX_WAIT_SEMAPHORES;
    swapchain_state_t *states[MAX_SWAPCHAINS_PER_PRESENT];
    for (uint32_t i = 0; all_ready && i < n; i++) {
        swapchain_state_t *sc = find_swapchain(dd, present_info->pSwapchains[i]);
        if (!sc || !sc->overlay_ready) {
            all_ready = false;
            break;
        }
        states[i] = sc;
    }

    if (!all_ready) {
        return dd->QueuePresentKHR(queue, present_info);
    }

    VkCommandBuffer cmd_buffers[MAX_SWAPCHAINS_PER_PRESENT];
    VkSemaphore signal_semaphores[MAX_SWAPCHAINS_PER_PRESENT];
    for (uint32_t i = 0; i < n; i++) {
        uint32_t image_index = present_info->pImageIndices[i];
        cmd_buffers[i] = states[i]->command_buffers[image_index];
        signal_semaphores[i] = states[i]->layer_semaphores[image_index];
    }

    VkPipelineStageFlags wait_stages[MAX_WAIT_SEMAPHORES];
    for (uint32_t i = 0; i < present_info->waitSemaphoreCount; i++) {
        /* We don't know what stage the application's own semaphore
         * signals at, so wait for everything -- always correct, only
         * ever over-conservative. */
        wait_stages[i] = VK_PIPELINE_STAGE_ALL_COMMANDS_BIT;
    }

    VkSubmitInfo submit = {
        .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
        .waitSemaphoreCount = present_info->waitSemaphoreCount,
        .pWaitSemaphores = present_info->pWaitSemaphores,
        .pWaitDstStageMask = wait_stages,
        .commandBufferCount = n,
        .pCommandBuffers = cmd_buffers,
        .signalSemaphoreCount = n,
        .pSignalSemaphores = signal_semaphores,
    };

    VkResult submit_result = dd->QueueSubmit(dd->present_queue, 1, &submit, VK_NULL_HANDLE);
    if (submit_result != VK_SUCCESS) {
        /* The "presented frames remain valid" requirement: our drawing
         * work failed, so fall through exactly as if this layer were
         * not here, on the application's own wait semaphores. */
        return dd->QueuePresentKHR(queue, present_info);
    }

    VkPresentInfoKHR real_present = *present_info;
    real_present.waitSemaphoreCount = n;
    real_present.pWaitSemaphores = signal_semaphores;
    return dd->QueuePresentKHR(queue, &real_present);
}

/* ------------------------------------------------------------------ */
/* Loader-facing exports                                               */
/* ------------------------------------------------------------------ */

VK_LAYER_EXPORT VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL
vkGetInstanceProcAddr(VkInstance instance, const char *name) {
    if (strcmp(name, "vkGetInstanceProcAddr") == 0) {
        return (PFN_vkVoidFunction)vkGetInstanceProcAddr;
    }
    if (strcmp(name, "vkCreateInstance") == 0) {
        return (PFN_vkVoidFunction)boresight_CreateInstance;
    }
    if (strcmp(name, "vkDestroyInstance") == 0) {
        return (PFN_vkVoidFunction)boresight_DestroyInstance;
    }
    if (strcmp(name, "vkCreateDevice") == 0) {
        return (PFN_vkVoidFunction)boresight_CreateDevice;
    }

    if (!instance) {
        return NULL;
    }
    instance_data_t *data = find_instance(GET_KEY(instance));
    if (!data) {
        return NULL;
    }
    return data->gipa(instance, name);
}

VK_LAYER_EXPORT VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL
vkGetDeviceProcAddr(VkDevice device, const char *name) {
    if (strcmp(name, "vkGetDeviceProcAddr") == 0) {
        return (PFN_vkVoidFunction)vkGetDeviceProcAddr;
    }
    if (strcmp(name, "vkDestroyDevice") == 0) {
        return (PFN_vkVoidFunction)boresight_DestroyDevice;
    }
    if (strcmp(name, "vkCreateSwapchainKHR") == 0) {
        return (PFN_vkVoidFunction)boresight_CreateSwapchainKHR;
    }
    if (strcmp(name, "vkDestroySwapchainKHR") == 0) {
        return (PFN_vkVoidFunction)boresight_DestroySwapchainKHR;
    }
    if (strcmp(name, "vkQueuePresentKHR") == 0) {
        return (PFN_vkVoidFunction)boresight_QueuePresentKHR;
    }

    device_data_t *data = find_device(GET_KEY(device));
    if (!data) {
        return NULL;
    }
    return data->gdpa(device, name);
}

VK_LAYER_EXPORT VKAPI_ATTR VkResult VKAPI_CALL
vkNegotiateLoaderLayerInterfaceVersion(VkNegotiateLayerInterface *interface_struct) {
    if (!interface_struct ||
        interface_struct->sType != LAYER_NEGOTIATE_INTERFACE_STRUCT) {
        return VK_ERROR_INITIALIZATION_FAILED;
    }

    if (interface_struct->loaderLayerInterfaceVersion >= 2) {
        interface_struct->pfnGetInstanceProcAddr = vkGetInstanceProcAddr;
        interface_struct->pfnGetDeviceProcAddr = vkGetDeviceProcAddr;
        interface_struct->pfnGetPhysicalDeviceProcAddr = NULL;
    }

    if (interface_struct->loaderLayerInterfaceVersion > CURRENT_LOADER_LAYER_INTERFACE_VERSION) {
        interface_struct->loaderLayerInterfaceVersion = CURRENT_LOADER_LAYER_INTERFACE_VERSION;
    } else if (interface_struct->loaderLayerInterfaceVersion < 1) {
        return VK_ERROR_INITIALIZATION_FAILED;
    }

    return VK_SUCCESS;
}
