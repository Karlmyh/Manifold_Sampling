
import logging
import numpy as np
import sys


__all__ = ['sumsq', 'eval_least_squares_objective', 'model_value', 'random_orthog_directions_within_bounds',
           'random_directions_within_bounds', 'apply_scaling', 'remove_scaling','L2']



def sumsq(x):
    # There are several ways to calculate sum of squares of a vector:
    #   np.dot(x,x)
    #   np.sum(x**2)
    #   np.sum(np.square(x))
    #   etc.
    # Using the timeit routine, it seems like dot(x,x) is ~3-4x faster than other methods
    return np.dot(x, x)

def L2(x):
    return np.sqrt(sumsq(x))


def eval_least_squares_objective(objfun, x, args=(), verbose=True, eval_num=0, pt_num=0, full_x_thresh=6, check_for_overflow=True):
    # Evaluate least squares function
    fvec = objfun(x, *args)

    if check_for_overflow:
        try:
            if np.max(np.abs(fvec)) >= np.sqrt(sys.float_info.max):
                f = sys.float_info.max
            else:
                f = sumsq(fvec)  # objective = sum(ri^2) [no 1/2 factor at front]
        except OverflowError:
            f = sys.float_info.max
    else:
        f = sumsq(fvec)

    if verbose:
        if len(x) < full_x_thresh:
            logging.info("Function eval %i at point %i has f = %.15g at x = " % (eval_num, pt_num, f) + str(x))
        else:
            logging.info("Function eval %i at point %i has f = %.15g at x = [...]" % (eval_num, pt_num, f))

    return fvec, f


def model_value(g, H, s):
    # Calculate model value (s^T * g + 0.5* s^T * H * s) = s^T * (gopt + 0.5 * H*s)
    assert g.shape == s.shape, "g and s have incompatible sizes"
    Hs = H.dot(s)
    return np.dot(s, g + 0.5*Hs)


def get_scale(dirn, delta, lower, upper):
    scale = delta
    for j in range(len(dirn)):
        if dirn[j] < 0.0:
            scale = min(scale, lower[j] / dirn[j])
        elif dirn[j] > 0.0:
            scale = min(scale, upper[j] / dirn[j])
    return scale


def random_orthog_directions_within_bounds(num_pts, delta, lower, upper, with_neg_dirns=True):
    # Generate num_pts random directions d1, d2, ...
    # so that lower <= d1 <= upper and ||d1|| ~ delta [perhaps not equal if constraint active]
    # Try to encourage a 'star shape' of orthogonal directions first
    # then completely random after that.
    n = len(lower)
    assert lower.shape == (n,), "lower must be a vector"
    assert upper.shape == (n,), "lower and upper have incompatible sizes"
    assert np.min(upper) >= -1e-15, "upper must be non-negative"
    assert np.max(lower) <= 1e-15, "lower must be non-positive"
    assert np.min(upper - lower) > 0.0, "upper must be > lower"
    assert delta > 0, "delta must be strictly positive"
    assert num_pts > 0, "num_pts must be strictly positive"
    if with_neg_dirns:
        results = np.zeros((n, max(2*n, num_pts)))  # save space for results
    else:
        results = np.zeros((n, max(n, num_pts)))  # save space for results
    # Find the active set
    idx_l = (lower == 0)
    idx_u = (upper == 0)
    active = np.logical_or(idx_l, idx_u)
    inactive = np.logical_not(active)
    nactive = np.sum(active)
    ninactive = n - nactive
    # Get a random orthonormal basis for the inactive variables
    if ninactive > 0:
        A = np.random.normal(size=(ninactive, ninactive))
        Qred = np.linalg.qr(A)[0]  # orthonormal columns (reduced)
        Q = np.zeros((n, ninactive))  # full set of orthonormal vectors
        Q[inactive, :] = Qred  # zero change for active variables
        # 1. Orthogonal directions
        for i in range(ninactive):
            scale = get_scale(Q[:,i], delta, lower, upper)
            results[:, i] = scale * Q[:, i]
    # 2. Directions for active constraints
    idx_active = np.where(active)[0]  # indices of active constraints
    for i in range(nactive):
        idx = idx_active[i]
        results[idx, ninactive+i] = 1.0 if idx_l[idx] else -1.0
        results[:, ninactive+i] = get_scale(results[:, ninactive+i], delta, lower, upper) * results[:, ninactive+i]
    # 3. Negative orthogonal directions
    if with_neg_dirns:
        for i in range(ninactive):
            scale = get_scale(-Q[:, i], delta, lower, upper)
            results[:, n+i] = -scale * Q[:, i]
        # 4. Extra directions for active constraints
        for i in range(nactive):
            idx = idx_active[i]
            sign = 1.0 if idx_l[idx] else -1.0  # desired sign of direction shift
            if upper[idx] - lower[idx] > delta:
                results[idx, n+ninactive+i] = 2.0 * sign * delta
            else:
                results[idx, n + ninactive + i] = 0.5 * sign * (upper[idx] - lower[idx])
                # To get correct scaling, don't use delta any more (too big), use the scaling as given by upper-lower
            results[:, n+ninactive+i] = get_scale(results[:, n+ninactive+i], 1.0, lower, upper)*results[:, n+ninactive+i]
    # 5. Pad out the rest with random extra directions
    for i in range(num_pts - (2*n if with_neg_dirns else n)):
        dirn = np.random.normal(size=(n,))
        for j in range(nactive):
            idx = idx_active[j]
            sign = 1.0 if idx_l[idx] else -1.0  # desired sign of direction shift
            if dirn[idx]*sign < 0.0:
                dirn[idx] *= -1.0
        dirn = dirn / np.linalg.norm(dirn)
        scale = get_scale(dirn, delta, lower, upper)
        results[:, (2*n if with_neg_dirns else n)+i] = dirn * scale
    # Finally, make sure everything is within bounds
    for i in range(num_pts):
        results[:, i] = np.maximum(np.minimum(results[:, i], upper), lower)
    return results[:, :num_pts].T


def random_directions_within_bounds(num_pts, delta, lower, upper):
    # Generate num_pts random directions d1, d2, ...
    # so that lower <= d1 <= upper and ||d1|| ~ delta [perhaps not equal if constraint active]
    # Directions should be completely random (as much as possible while staying within bounds)
    n = len(lower)
    assert lower.shape == (n,), "lower must be a vector"
    assert upper.shape == (n,), "lower and upper have incompatible sizes"
    assert np.min(upper) >= -1e-15, "upper must be non-negative"
    assert np.max(lower) <= 1e-15, "lower must be non-positive"
    assert np.min(upper - lower) > 0.0, "upper must be > lower"
    assert delta > 0, "delta must be strictly positive"
    assert num_pts > 0, "num_pts must be strictly positive"
    results = np.zeros((n, num_pts))  # save space for results
    # Find the active set
    idx_l = (lower == 0)
    idx_u = (upper == 0)
    active = np.logical_or(idx_l, idx_u)
    # inactive = np.logical_not(active)
    nactive = np.sum(active)
    # ninactive = n - nactive
    idx_active = np.where(active)[0]  # indices of active constraints
    for i in range(num_pts):
        dirn = np.random.normal(size=(n,))
        for j in range(nactive):
            idx = idx_active[j]
            sign = 1.0 if idx_l[idx] else -1.0  # desired sign of direction shift
            if dirn[idx]*sign < 0.0:
                dirn[idx] *= -1.0
        dirn = dirn / np.linalg.norm(dirn)
        scale = get_scale(dirn, delta, lower, upper)
        results[:, i] = dirn * scale
    # Finally, scale by delta and make sure everything is within bounds
    for i in range(num_pts):
        results[:, i] = np.maximum(np.minimum(results[:, i], upper), lower)
    return results.T


def apply_scaling(x_raw, scaling_changes):
    if scaling_changes is None:
        return x_raw
    shift, scale = scaling_changes
    return (x_raw - shift) / scale


def remove_scaling(x_scaled, scaling_changes):
    if scaling_changes is None:
        return x_scaled
    shift, scale = scaling_changes
    return shift + x_scaled * scale

